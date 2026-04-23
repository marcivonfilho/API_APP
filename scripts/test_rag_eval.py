import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.rag.knowledge_index import KnowledgeIndex
from app.rag.intents import classify_technical_intent
from app.rag.normative_map import search_terms_for_intent
from app.rag.query_expansion import preferred_content_types
from app.rag.query_profile import build_query_profile


def safe_console(value: str) -> str:
    return value.encode("ascii", errors="replace").decode("ascii")


QUESTIONS = [
    ("O que e pressao interna?", {"9", "43", "44", "45"}),
    ("O que e pressao externa?", {"9"}),
    ("O que e pressao dinamica?", {"6", "8"}),
    ("O que e velocidade caracteristica?", {"4", "8"}),
    ("O que e velocidade basica do vento?", {"4", "10"}),
    ("O que e coeficiente de pressao interna?", {"9", "43", "44", "45"}),
    ("O que e coeficiente de forma?", {"3", "9"}),
    ("O que e S1?", {"4", "10"}),
    ("O que e S2?", {"4", "14", "16", "18", "87"}),
    ("O que e S3?", {"4", "17", "92"}),
    ("Qual e a formula da velocidade caracteristica do vento?", {"4", "8"}),
    ("Qual e a formula da pressao dinamica q?", {"8"}),
]


INTENT_QUESTIONS = [
    ("Qual formula e mais importante?", "orientacao_normativa"),
    ("Por onde comeco para calcular o vento em uma edificacao?", "orientacao_normativa"),
    ("Qual coeficiente devo usar para pressao interna?", "selecao_normativa"),
    ("Como calcular a acao do vento passo a passo?", "procedimento"),
    ("Qual fator eu aplico primeiro?", "orientacao_normativa"),
]


PROFILE_QUESTIONS = [
    ("Qual formula e mais importante?", "orientacao_normativa"),
    ("Por onde comeco para calcular o vento em uma edificacao?", "orientacao_normativa"),
    ("Qual coeficiente devo usar para pressao interna?", "selecao_normativa"),
    ("Como calcular a acao do vento passo a passo?", "procedimento"),
]


def main() -> None:
    index = KnowledgeIndex(BASE_DIR)
    failures = []

    for question, expected_pages in QUESTIONS:
        types = preferred_content_types(question)
        if not types:
            types = {"texto", "formula"}
        results = index.search(
            question,
            limit=3,
            collections={"norma"},
            content_types=types | {"texto", "formula"},
        )
        print(f"\nPERGUNTA: {question}")
        if not results:
            failures.append(question)
            print("  SEM RESULTADOS")
            continue
        returned_pages = {
            str((item.get("metadata") or {}).get("pagina") or "")
            for item in results
        }
        if expected_pages and not (returned_pages & expected_pages):
            failures.append(question)
            print(f"  ALERTA: paginas esperadas nao retornaram. Esperado: {sorted(expected_pages)}")
        for idx, item in enumerate(results, start=1):
            metadata = item.get("metadata") or {}
            preview = safe_console((item.get("documento") or "").replace("\n", " ")[:160])
            print(
                f"  {idx}. p.{metadata.get('pagina')} "
                f"secao {metadata.get('secao')} "
                f"tipo {metadata.get('tipo_conteudo')} "
                f"score {item.get('lexical_score'):.2f}"
            )
            print(f"     {preview}")

    print("\nTESTE DE INTENCAO TECNICA")
    for question, expected_intent in INTENT_QUESTIONS:
        intent = classify_technical_intent(question)
        print(f"  {question} -> {intent.name}")
        if intent.name != expected_intent:
            failures.append(f"{question} intent={intent.name} expected={expected_intent}")

        guided_terms = search_terms_for_intent(intent.name, question)
        if expected_intent != "desconhecida" and not guided_terms:
            failures.append(f"{question} sem termos guiados")

    print("\nTESTE DE PERFIL RAG")
    for question, expected_profile in PROFILE_QUESTIONS:
        profile = build_query_profile(question, default_fetch_k=18)
        print(f"  {question} -> profile={profile.intent}")
        if profile.intent != expected_profile:
            failures.append(f"{question} profile={profile.intent} expected={expected_profile}")

    if failures:
        raise SystemExit(f"Falhas de recuperacao: {failures}")

    print("\nAvaliacao lexical concluida sem falhas.")


if __name__ == "__main__":
    main()
