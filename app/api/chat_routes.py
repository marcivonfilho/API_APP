from pathlib import Path
import json
from time import perf_counter

from flask import Blueprint, Response, jsonify, request

from app.rag.service import RagChatService


try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    load_dotenv = None

if load_dotenv:
    load_dotenv()

chat_bp = Blueprint("chat", __name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CHROMA_PATH = BASE_DIR / "vector_db" / "chroma_db"
_rag_service = None


def get_rag_service():
    global _rag_service
    if _rag_service is None:
        _rag_service = RagChatService(
            base_dir=BASE_DIR,
            chroma_path=CHROMA_PATH,
        )
    return _rag_service


def _extract_question(dados: dict) -> str:
    return (
        dados.get("pergunta")
        or dados.get("message")
        or dados.get("mensagem")
        or dados.get("question")
        or ""
    ).strip()


def _format_chat_response(resposta: dict, include_debug: bool = False) -> dict:
    fontes = resposta.get("fontes") or []
    payload = {
        "ok": True,
        "resposta": resposta.get("resposta_markdown", ""),
        "resposta_markdown": resposta.get("resposta_markdown", ""),
        "fontes": fontes,
        "modelo": resposta.get("modelo"),
        "modo": resposta.get("modo"),
    }

    if resposta.get("uso") is not None:
        payload["uso"] = resposta.get("uso")

    if resposta.get("response_id") is not None:
        payload["response_id"] = resposta.get("response_id")

    if resposta.get("previous_response_id") is not None:
        payload["previous_response_id"] = resposta.get("previous_response_id")

    if resposta.get("calculo") is not None:
        payload["calculo"] = resposta.get("calculo")

    if resposta.get("v0_lookup") is not None:
        payload["v0_lookup"] = resposta.get("v0_lookup")

    if include_debug:
        payload["trechos_recuperados"] = resposta.get("trechos_recuperados", [])
        payload["orquestracao"] = resposta.get("orquestracao")

    return payload


def _format_sources(fontes: list[dict]) -> list[str]:
    formatted = []
    seen = set()
    for fonte in fontes:
        nome = fonte.get("fonte") or "Fonte tecnica"
        secao = fonte.get("secao") or ""
        pagina = fonte.get("pagina") or ""
        parts = [str(nome)]
        if secao:
            parts.append(f"Sec. {secao}")
        if pagina:
            parts.append(f"p. {pagina}")
        label = " · ".join(parts)
        if label not in seen:
            seen.add(label)
            formatted.append(label)
    return formatted


def _format_sources_latex(fontes: list[dict]) -> str:
    labels = _format_sources(fontes)
    if not labels:
        return ""
    joined = r"\; \cdot \;".join(_escape_latex_text(label) for label in labels[:4])
    return rf"$$\small{{\text{{Fonte normativa: {joined}}}}}$$"


def _format_sources_markdown(fontes: list[dict]) -> str:
    latex = _format_sources_latex(fontes)
    if not latex:
        return ""
    return latex


def _escape_latex_text(value: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "{": r"\{",
        "}": r"\}",
        "_": r"\_",
        "&": r"\&",
        "%": r"\%",
        "#": r"\#",
        "$": r"\$",
    }
    return "".join(replacements.get(char, char) for char in value)


def _build_conversation_context(dados: dict) -> str:
    if dados.get("previous_response_id") or dados.get("last_response_id"):
        force_context = bool(dados.get("force_context", False))
        has_state = dados.get("last_v0") is not None or dados.get("last_geo_label")
        if not force_context and not has_state:
            return ""

    parts = []
    summary = (dados.get("summary") or dados.get("resumo") or "").strip()
    last_user = (dados.get("last_user_message") or dados.get("ultima_pergunta") or "").strip()
    last_assistant = (dados.get("last_assistant_message") or dados.get("ultima_resposta") or "").strip()
    user_id = (dados.get("user_id") or dados.get("usuario_id") or "").strip()
    device_id = (dados.get("device_id") or "").strip()
    last_v0 = dados.get("last_v0")
    last_geo_label = (dados.get("last_geo_label") or "").strip()

    if user_id:
        parts.append(f"Usuario/app id: {user_id}.")
    if device_id:
        parts.append(f"Device/session id: {device_id}.")
    if summary:
        parts.append(f"Resumo tecnico anterior:\n{summary}")
    if last_user:
        parts.append(f"Ultima pergunta relevante do usuario:\n{last_user}")
    if last_assistant:
        parts.append(f"Ultima resposta relevante do assistente:\n{last_assistant}")
    if last_v0 is not None:
        label = f" para {last_geo_label}" if last_geo_label else ""
        parts.append(f"Ultimo V0 confirmado{label}: {last_v0} m/s.")

    return "\n\n".join(parts)


def _build_request_metadata(dados: dict) -> dict:
    metadata = {}
    user_id = (dados.get("user_id") or dados.get("usuario_id") or "").strip()
    device_id = (dados.get("device_id") or "").strip()
    thread_id = (dados.get("thread_id") or dados.get("conversation_id") or "").strip()

    if user_id:
        metadata["user_id"] = user_id[:512]
    if device_id:
        metadata["device_id"] = device_id[:512]
    if thread_id:
        metadata["thread_id"] = thread_id[:512]

    return metadata


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _handle_chat_request():
    dados = request.get_json(silent=True) or {}
    pergunta_usuario = _extract_question(dados)
    include_debug = bool(dados.get("debug", False))

    if not pergunta_usuario:
        return jsonify({
            "ok": False,
            "erro": "Nenhuma pergunta enviada.",
            "detalhe": "Envie um JSON com o campo 'pergunta' ou 'message'.",
        }), 400

    started_at = perf_counter()
    try:
        resposta = get_rag_service().answer(
            pergunta=pergunta_usuario,
            previous_response_id=(
                dados.get("previous_response_id")
                or dados.get("last_response_id")
                or None
            ),
            conversation_context=_build_conversation_context(dados),
            request_metadata=_build_request_metadata(dados),
        )
        payload = _format_chat_response(resposta, include_debug=include_debug)
        payload["tempo_ms"] = round((perf_counter() - started_at) * 1000, 2)
        return jsonify(payload), 200
    except Exception as e:
        print(f"Erro no RAG: {e}")
        detalhe = str(e)
        if "does not exist" in detalhe.lower() or "collection" in detalhe.lower():
            detalhe = (
                "Base vetorial nao encontrada. Rode `python scripts/ingestao_chroma.py` "
                "depois de executar o extrator."
            )
        return jsonify({
            "ok": False,
            "erro": "Falha ao gerar a resposta.",
            "detalhe": detalhe,
        }), 500


@chat_bp.route("/api/perguntar", methods=["POST"])
def fazer_pergunta():
    return _handle_chat_request()


@chat_bp.route("/api/chat", methods=["POST"])
def chat_app():
    return _handle_chat_request()


@chat_bp.route("/chat/stream_v2", methods=["POST"])
def chat_stream_v2():
    dados = request.get_json(silent=True) or {}
    pergunta_usuario = _extract_question(dados)
    previous_response_id = (
        dados.get("previous_response_id")
        or dados.get("last_response_id")
        or None
    )
    include_debug = bool(dados.get("debug", False))

    if not pergunta_usuario:
        return Response(
            _sse_event("error", {
                "ok": False,
                "erro": "Nenhuma pergunta enviada.",
                "detalhe": "Envie um JSON com o campo 'message' ou 'pergunta'.",
            }),
            status=400,
            mimetype="text/event-stream",
        )

    def generate():
        full_answer = ""
        response_obj = None
        usage = None
        started_at = perf_counter()

        try:
            request_params, metadata = get_rag_service().build_response_request(
                pergunta=pergunta_usuario,
                previous_response_id=previous_response_id,
                conversation_context=_build_conversation_context(dados),
                request_metadata=_build_request_metadata(dados),
            )

            with get_rag_service().openai_client.responses.stream(**request_params) as stream:
                for event in stream:
                    if event.type == "response.output_text.delta":
                        chunk = event.delta
                        full_answer += chunk
                        yield _sse_event("chunk", {"text": chunk})

                    candidate_response = getattr(event, "response", None)
                    if candidate_response is not None:
                        response_obj = candidate_response

            if response_obj is not None:
                usage_obj = getattr(response_obj, "usage", None)
                usage = usage_obj.model_dump() if usage_obj else None

            meta_payload = {
                "ok": True,
                "response_id": getattr(response_obj, "id", None),
                "previous_response_id": previous_response_id,
                "resposta": full_answer,
                "resposta_markdown": full_answer,
                "modelo": metadata.get("modelo"),
                "modo": metadata.get("modo"),
                "fontes": metadata.get("fontes", []),
                "uso": usage,
                "tempo_ms": round((perf_counter() - started_at) * 1000, 2),
            }
            if metadata.get("calculo") is not None:
                meta_payload["calculo"] = metadata.get("calculo")
            if metadata.get("v0_lookup") is not None:
                meta_payload["v0_lookup"] = metadata.get("v0_lookup")
            if include_debug:
                meta_payload["trechos_recuperados"] = metadata.get("trechos_recuperados", [])
                meta_payload["orquestracao"] = metadata.get("orquestracao")

            yield _sse_event("meta", meta_payload)
            yield _sse_event("done", {})

        except Exception as e:
            print(f"Erro no chat stream v2: {e}")
            yield _sse_event("error", {
                "ok": False,
                "erro": "Falha ao gerar a resposta em streaming.",
                "detalhe": str(e),
            })
            yield _sse_event("done", {})

    return Response(generate(), mimetype="text/event-stream")


@chat_bp.route("/api/chat/health", methods=["GET"])
def chat_health():
    try:
        service = get_rag_service()
        norma_count = service.norma_collection.count()
        artigos_count = service.article_collection.count() if service.article_collection is not None else 0
        return jsonify({
            "ok": True,
            "collections": {
                "norma": {
                    "name": service.norma_collection_name,
                    "documents": norma_count,
                },
                "artigos": {
                    "name": service.artigos_collection_name,
                    "documents": artigos_count,
                    "available": service.article_collection is not None,
                },
            },
            "model": service.model_name,
        }), 200
    except Exception as e:
        return jsonify({
            "ok": False,
            "erro": "Chat RAG indisponivel.",
            "detalhe": str(e),
        }), 500
