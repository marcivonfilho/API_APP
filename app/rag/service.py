import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chromadb
from openai import OpenAI

from app.calculos.engine import CalculationEngine
from app.llm.prompts import (
    CALCULATION_SYSTEM_INSTRUCTION,
    RAG_SYSTEM_INSTRUCTION,
    build_calculation_prompt,
    build_rag_user_prompt,
)
from app.orchestrator.chat_orchestrator import ChatOrchestrator
from app.orchestrator.selection_policy import (
    is_selection_source_relevant,
    selection_relevance_score,
    selection_target_name,
)
from app.rag.embeddings import get_embedding_function
from app.rag.ingestion import ARTIGOS_COLLECTION_NAME, NORMA_COLLECTION_NAME
from app.rag.intents import classify_technical_intent
from app.rag.knowledge_index import KnowledgeIndex
from app.rag.normative_map import guidance_for_question, search_terms_for_intent
from app.rag.query_profile import build_query_profile
from app.rag.query_expansion import is_short_normative_query, preferred_content_types
from app.tools.v0_lookup.service import V0LookupService


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class QueryProfile:
    intent: str
    intents: set[str]
    strict: bool
    fetch_k: int
    max_items: int
    max_doc_chars: int
    context_max_chars: int
    max_output_tokens: int
    type_targets: list[tuple[str, int]]
    collections: list[str]


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return ascii_text.lower()


def _query_intent(question: str) -> set[str]:
    text = _normalize_text(question)
    intents: set[str] = {"texto"}
    if re.search(r"\b(calcul|formula|fórmula|equacao|equação|pressao dinamica|pressão dinâmica|forca|força|vk|v_k|q\b)", text):
        intents.add("formula")
    if any(term in text for term in [
        "velocidade caracteristica",
        "fator topografico",
        "fator estatistico",
        "fator s1",
        "fator s2",
        "fator s3",
    ]):
        intents.add("formula")
    if re.search(r"\b(tabela|valor|coeficiente|s1|s2|s3|categoria|classe|rugosidade)\b", text):
        intents.add("tabela")
    if re.search(r"\b(figura|grafico|isopleta|mapa|curva)\b", text):
        intents.add("figura")
    if re.search(r"\b(artigo|proposta|atualizacao|atualização|isopleta)\b", text):
        intents.add("artigo")
    for content_type in preferred_content_types(question):
        if content_type == "formula":
            intents.add("formula")
        elif content_type == "tabela":
            intents.add("tabela")
        elif content_type == "figura":
            intents.add("figura")
    return intents


def _build_query_profile(question: str, default_fetch_k: int) -> QueryProfile:
    normalized = _normalize_text(question)
    intents = _query_intent(question)
    technical_intent = classify_technical_intent(question)
    strict = bool(re.search(r"\b(apenas|somente|so|só|sem explicacao|sem explicação|direto|responda curto)\b", normalized))
    is_definition = bool(re.search(r"\b(o que e|o que é|defina|definicao|definição)\b", normalized))

    is_calc = bool(re.search(r"\b(calcule|calcular|calculo|cálculo|determine|determinar)\b", normalized))
    is_table = "tabela" in intents and not is_calc
    is_formula = "formula" in intents and not is_calc
    is_figure = "figura" in intents
    is_comparison = bool(re.search(r"\b(compare|comparar|comparacao|comparação|diferen|versus|vs)\b", normalized))
    is_normative_term = is_short_normative_query(question)

    if is_calc:
        return QueryProfile(
            intent="calculo",
            intents=intents,
            strict=False,
            fetch_k=min(default_fetch_k, 12),
            max_items=4,
            max_doc_chars=1400,
            context_max_chars=5500,
            max_output_tokens=800,
            type_targets=[("formula", 2), ("tabela", 1), ("texto", 1)],
            collections=["norma"],
        )

    if technical_intent.name in {"orientacao_normativa", "procedimento", "selecao_normativa"}:
        intents.update({"formula", "tabela"})
        selection_target = selection_target_name(question)
        if technical_intent.name == "selecao_normativa" and selection_target not in {"coeficiente_pressao_interna", "formula_fluxo"}:
            intents.add("figura")
        return QueryProfile(
            intent=technical_intent.name,
            intents=intents,
            strict=strict,
            fetch_k=min(default_fetch_k, 14),
            max_items=4 if technical_intent.name == "selecao_normativa" else 5,
            max_doc_chars=1000 if technical_intent.name == "selecao_normativa" else 1400,
            context_max_chars=5200 if technical_intent.name == "selecao_normativa" else 7200,
            max_output_tokens=750 if technical_intent.name == "selecao_normativa" else 1100,
            type_targets=[("texto", 2), ("formula", 1), ("tabela", 1), ("figura", 1)],
            collections=["norma"],
        )

    if is_normative_term:
        return QueryProfile(
            intent="termo_normativo",
            intents=intents,
            strict=strict,
            fetch_k=min(default_fetch_k, 12),
            max_items=5,
            max_doc_chars=1400,
            context_max_chars=6200,
            max_output_tokens=850,
            type_targets=[("texto", 2), ("formula", 1), ("tabela", 1), ("texto", 1)],
            collections=["norma"],
        )

    if is_table:
        return QueryProfile(
            intent="tabela",
            intents=intents,
            strict=strict,
            fetch_k=min(default_fetch_k, 12),
            max_items=4,
            max_doc_chars=1800,
            context_max_chars=6500,
            max_output_tokens=1000,
            type_targets=[("tabela", 2), ("texto", 2)],
            collections=["norma"],
        )

    if is_formula:
        return QueryProfile(
            intent="formula",
            intents=intents,
            strict=strict,
            fetch_k=min(default_fetch_k, 10),
            max_items=3,
            max_doc_chars=1200,
            context_max_chars=4200,
            max_output_tokens=1000,
            type_targets=[("formula", 1), ("texto", 2)],
            collections=["norma"],
        )

    if "artigo" in intents:
        collections = ["norma", "artigos"] if is_comparison else ["artigos"]
        return QueryProfile(
            intent="comparacao" if is_comparison else "artigo",
            intents=intents,
            strict=strict,
            fetch_k=min(default_fetch_k, 10),
            max_items=4 if is_comparison else 3,
            max_doc_chars=1800,
            context_max_chars=6500 if is_comparison else 5200,
            max_output_tokens=1300,
            type_targets=[("texto", 4 if is_comparison else 3)],
            collections=collections,
        )

    if is_figure:
        return QueryProfile(
            intent="figura",
            intents=intents,
            strict=strict,
            fetch_k=min(default_fetch_k, 10),
            max_items=3,
            max_doc_chars=1400,
            context_max_chars=4500,
            max_output_tokens=1000,
            type_targets=[("figura", 1), ("texto", 2)],
            collections=["norma"],
        )

    if is_definition:
        if "formula" in intents or "tabela" in intents:
            return QueryProfile(
                intent="termo_normativo",
                intents=intents,
                strict=strict,
                fetch_k=min(default_fetch_k, 12),
                max_items=5,
                max_doc_chars=1400,
                context_max_chars=6200,
                max_output_tokens=850,
                type_targets=[("texto", 2), ("formula", 1), ("tabela", 1), ("texto", 1)],
                collections=["norma"],
            )
        return QueryProfile(
            intent="definicao",
            intents=intents,
            strict=strict,
            fetch_k=min(default_fetch_k, 8),
            max_items=1,
            max_doc_chars=1500,
            context_max_chars=1800,
            max_output_tokens=450,
            type_targets=[("texto", 1)],
            collections=["norma"],
        )

    return QueryProfile(
        intent="conceito",
        intents=intents,
        strict=strict,
        fetch_k=min(default_fetch_k, 10),
        max_items=2,
        max_doc_chars=1400,
        context_max_chars=2800,
        max_output_tokens=600,
        type_targets=[("texto", 2)],
        collections=["norma"],
    )


_build_query_profile = build_query_profile


def _infer_section_from_document(document: str, question: str, fallback: str = "") -> str:
    headings = list(re.finditer(r"(?m)^#{1,4}\s+(\d+(?:\.\d+)*)(?:\s+(.+))?$", document or ""))
    if not headings:
        return fallback or ""

    terms = {
        "velocidade basica": "velocidade básica",
        "velocidade básica": "velocidade básica",
        "v0": "velocidade básica",
        "v_0": "velocidade básica",
        "pressao dinamica": "pressão dinâmica",
        "pressão dinâmica": "pressão dinâmica",
        "s1": "fator topográfico",
        "s_1": "fator topográfico",
        "s2": "rugosidade",
        "s_2": "rugosidade",
        "s3": "fator estatístico",
        "s_3": "fator estatístico",
    }
    normalized_question = question.lower()
    wanted_terms = [
        target for key, target in terms.items()
        if key in normalized_question
    ]

    for heading in headings:
        title = (heading.group(2) or "").lower()
        if any(term in title for term in wanted_terms):
            return heading.group(1)

    first_specific = next(
        (heading.group(1) for heading in headings if "." in heading.group(1)),
        headings[0].group(1),
    )
    return first_specific or fallback or ""


class RagChatService:
    def __init__(
        self,
        base_dir: Path,
        chroma_path: Path,
        collection_name: str | None = None,
        model_name: str | None = None,
        n_results: int = 6,
    ):
        self.base_dir = base_dir
        self.chroma_path = chroma_path
        self.collection_name = collection_name or os.getenv(
            "RAG_COLLECTION_NAME",
            NORMA_COLLECTION_NAME,
        )
        self.norma_collection_name = os.getenv("RAG_NORMA_COLLECTION_NAME", NORMA_COLLECTION_NAME)
        self.artigos_collection_name = os.getenv("RAG_ARTIGOS_COLLECTION_NAME", ARTIGOS_COLLECTION_NAME)
        self.model_name = model_name or os.getenv("OPENAI_CHAT_MODEL", "gpt-5-mini")
        self.n_results = int(os.getenv("RAG_N_RESULTS", n_results))
        self.fetch_k = _env_int("RAG_FETCH_K", max(self.n_results * 3, 18))
        self.context_max_chars = _env_int("RAG_CONTEXT_MAX_CHARS", 14000)
        self.max_doc_chars = _env_int("RAG_MAX_DOC_CHARS", 2800)
        self.max_output_tokens = _env_int("RAG_MAX_OUTPUT_TOKENS", 1200)

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY nao encontrada no ambiente.")

        self.openai_client = OpenAI(api_key=api_key)
        self.orchestrator = ChatOrchestrator()
        self.calculation_engine = CalculationEngine()
        self.v0_lookup_service = V0LookupService()
        self.knowledge_index = KnowledgeIndex(self.base_dir)
        self.embedding_function = get_embedding_function()
        self.chroma_client = chromadb.PersistentClient(path=str(self.chroma_path))
        self.norma_collection = self.chroma_client.get_collection(
            name=self.norma_collection_name,
            embedding_function=self.embedding_function,
        )
        self.article_collection = None
        try:
            self.article_collection = self.chroma_client.get_collection(
                name=self.artigos_collection_name,
                embedding_function=self.embedding_function,
            )
        except Exception:
            self.article_collection = None
        self.collection = self.norma_collection

    def collections_for_profile(self, profile: QueryProfile) -> list[tuple[str, Any]]:
        collections: list[tuple[str, Any]] = []
        if "norma" in profile.collections:
            collections.append(("norma", self.norma_collection))
        if "artigos" in profile.collections and self.article_collection is not None:
            collections.append(("artigos", self.article_collection))
        return collections or [("norma", self.norma_collection)]

    def retrieve(self, pergunta: str) -> list[dict]:
        profile = _build_query_profile(pergunta, self.fetch_k)
        intents = profile.intents
        items: list[dict] = []
        for collection_label, collection in self.collections_for_profile(profile):
            items.extend(self.query_collection(pergunta, profile.fetch_k, collection, collection_label))

        for guided_query in search_terms_for_intent(profile.intent, pergunta):
            for collection_label, collection in self.collections_for_profile(profile):
                if collection_label != "norma":
                    continue
                items.extend(
                    self.query_collection(
                        guided_query,
                        max(4, self.n_results),
                        collection,
                        collection_label,
                    )
                )

        lexical_collections = set(profile.collections)
        lexical_types = preferred_content_types(pergunta)
        if profile.intent in {"termo_normativo", "definicao", "conceito"}:
            lexical_types.update({"texto", "formula"})
        if "tabela" in intents:
            lexical_types.add("tabela")
        if "figura" in intents:
            lexical_types.add("figura")

        items.extend(
            self.knowledge_index.search(
                pergunta,
                limit=max(10, profile.fetch_k),
                collections=lexical_collections,
                content_types=lexical_types,
            )
        )

        if profile.intent in {"termo_normativo", "orientacao_normativa", "procedimento", "selecao_normativa"}:
            seed_items = sorted(
                items,
                key=lambda item: self.score_item(pergunta, item, profile),
                reverse=True,
            )[:3]
            for item in seed_items:
                items.extend(
                    self.knowledge_index.related_by_page(
                        item,
                        limit=3,
                        content_types={"texto", "formula", "tabela"},
                    )
                )

        if "formula" in intents:
            formula_query = f"{pergunta} formula equacao V_k V0 S1 S2 S3 q"
            for collection_label, collection in self.collections_for_profile(profile):
                if collection_label != "norma":
                    continue
                items.extend(
                    self.query_collection(
                        formula_query,
                        max(6, self.n_results),
                        collection,
                        collection_label,
                        where={"tipo_conteudo": "formula"},
                    )
                )

        if "tabela" in intents:
            table_query = f"{pergunta} tabela valor coeficiente categoria classe"
            for collection_label, collection in self.collections_for_profile(profile):
                if collection_label != "norma":
                    continue
                items.extend(
                    self.query_collection(
                        table_query,
                        max(6, self.n_results),
                        collection,
                        collection_label,
                        where={"tipo_conteudo": "tabela"},
                    )
                )

        if "figura" in intents:
            for collection_label, collection in self.collections_for_profile(profile):
                items.extend(
                    self.query_collection(
                        pergunta,
                        max(4, self.n_results // 2),
                        collection,
                        collection_label,
                        where={"tipo_conteudo": "figura"},
                    )
                )

        return self.select_context_items(pergunta, items, profile)

    def build_sources(self, retrieved: list[dict], pergunta: str, profile: QueryProfile) -> list[dict]:
        fontes = []
        seen = set()
        source_items = list(retrieved)
        if profile.intent == "selecao_normativa":
            relevant_items = [
                item for item in source_items
                if is_selection_source_relevant(
                    pergunta,
                    item.get("documento") or "",
                    item.get("metadata") or {},
                )
            ]
            if relevant_items:
                source_items = sorted(
                    relevant_items,
                    key=lambda item: selection_relevance_score(
                        pergunta,
                        item.get("documento") or "",
                        item.get("metadata") or {},
                    ),
                    reverse=True,
                )

        max_sources = 4 if profile.intent == "selecao_normativa" else len(source_items)
        for item in source_items:
            if len(fontes) >= max_sources:
                break
            metadata = item["metadata"] or {}
            secao = _infer_section_from_document(
                item.get("documento", ""),
                pergunta,
                metadata.get("secao", ""),
            )
            key = (metadata.get("fonte"), metadata.get("pagina"), metadata.get("tipo_conteudo"), secao)
            if key in seen:
                continue
            seen.add(key)
            fontes.append({
                "fonte": metadata.get("fonte"),
                "pagina": metadata.get("pagina"),
                "tipo_conteudo": metadata.get("tipo_conteudo"),
                "secao": secao,
                "colecao": item.get("colecao", "norma"),
            })
        return fontes

    def query_collection(
        self,
        pergunta: str,
        n_results: int,
        collection: Any,
        collection_label: str,
        where: dict | None = None,
    ) -> list[dict]:
        query_kwargs = {
            "query_texts": [pergunta],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            query_kwargs["where"] = where

        result = collection.query(
            **query_kwargs,
        )

        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]

        items: list[dict] = []
        for document, metadata, distance in zip(documents, metadatas, distances):
            items.append({
                "documento": document,
                "metadata": metadata,
                "distancia": distance,
                "colecao": collection_label,
            })

        return items

    def select_context_items(
        self,
        pergunta: str,
        items: list[dict],
        profile: QueryProfile | None = None,
    ) -> list[dict]:
        profile = profile or _build_query_profile(pergunta, self.fetch_k)
        intents = profile.intents
        selected: list[dict] = []
        seen_keys = set()

        type_targets = list(profile.type_targets)
        if "artigo" in intents and not any(tipo == "artigo" for tipo, _ in type_targets):
            type_targets.append(("artigo", 1))

        allowed_types = {
            "texto",
            *(["formula"] if "formula" in intents else []),
            *(["tabela"] if "tabela" in intents else []),
            *(["figura"] if "figura" in intents else []),
        }

        def add_item(item: dict) -> bool:
            if len(selected) >= profile.max_items:
                return False
            metadata = item.get("metadata") or {}
            key = (
                metadata.get("fonte"),
                metadata.get("pagina"),
                metadata.get("secao"),
                metadata.get("tipo_conteudo"),
                metadata.get("formula_id") or metadata.get("titulo") or item.get("documento", "")[:80],
            )
            if key in seen_keys:
                return False
            seen_keys.add(key)
            selected.append(item)
            return True

        ranked_items = sorted(
            items,
            key=lambda item: self.score_item(pergunta, item, profile),
            reverse=True,
        )
        if profile.intent == "selecao_normativa":
            relevant_items = [
                item for item in ranked_items
                if is_selection_source_relevant(
                    pergunta,
                    item.get("documento") or "",
                    item.get("metadata") or {},
                )
            ]
            if relevant_items:
                ranked_items = relevant_items

        for tipo, target in type_targets:
            if target <= 0:
                continue
            matches = [
                item for item in ranked_items
                if (item.get("metadata") or {}).get("tipo_conteudo") == tipo
                or (tipo == "artigo" and (item.get("metadata") or {}).get("tipo_documento") == "artigo")
            ]
            for item in matches[:target]:
                if len(selected) >= profile.max_items:
                    break
                add_item(item)

        for item in ranked_items:
            if len(selected) >= profile.max_items:
                break
            metadata = item.get("metadata") or {}
            tipo = metadata.get("tipo_conteudo")
            tipo_documento = metadata.get("tipo_documento")
            if tipo not in allowed_types and not ("artigo" in intents and tipo_documento == "artigo"):
                continue
            add_item(item)

        return selected[:profile.max_items]

    def score_item(self, pergunta: str, item: dict, profile: QueryProfile) -> float:
        metadata = item.get("metadata") or {}
        document = item.get("documento") or ""
        tipo = metadata.get("tipo_conteudo") or ""
        fonte = metadata.get("fonte") or ""
        title = metadata.get("titulo") or ""
        haystack = _normalize_text(" ".join([document, title, str(metadata.get("secao", ""))]))
        question = _normalize_text(pergunta)

        distance = item.get("distancia")
        score = 0.0
        if isinstance(distance, (int, float)):
            score += max(0.0, 1.0 - float(distance)) * 2.0

        if "nbr 6123" in _normalize_text(fonte):
            score += 0.8
        elif profile.intent not in {"artigo", "comparacao"}:
            score -= 0.8
        if item.get("colecao") == "artigos" and profile.intent in {"artigo", "comparacao"}:
            score += 0.8

        if tipo == profile.type_targets[0][0]:
            score += 1.2
        if profile.intent == "termo_normativo":
            if tipo == "texto":
                score += 1.0
            elif tipo == "formula":
                score += 0.85
            elif tipo == "tabela":
                score += 0.55
        if profile.intent in {"orientacao_normativa", "procedimento", "selecao_normativa"}:
            if tipo == "formula":
                score += 1.0
            if any(term in haystack for term in ["v_k = v_0", "q = 0,613", "c_{pe}", "c_{pi}", "coeficiente de forma"]):
                score += 1.4
            if profile.intent == "selecao_normativa" and any(term in haystack for term in ["coeficiente", "tabela", "abertura", "permeabilidade"]):
                score += 1.2
            if profile.intent == "selecao_normativa":
                score += selection_relevance_score(pergunta, document, metadata) * 1.4
        if item.get("origem_busca") == "lexical":
            score += min(float(item.get("lexical_score") or 0.0), 60.0) / 12.0
        elif item.get("origem_busca") == "related_page":
            score += 0.75

        query_tokens = {
            token for token in re.findall(r"[a-z0-9_]{3,}", question)
            if token not in {"qual", "como", "para", "vento", "formula", "equacao", "norma"}
        }
        for token in query_tokens:
            if token in haystack:
                score += 0.35

        phrase_boosts = [
            (["velocidade basica", "v0", "v_0"], ["velocidade basica", "v_0", "v0", "rajada de 3 s", "50 anos"]),
            (["velocidade caracteristica", "vk", "v_k"], ["velocidade caracteristica", "v_k", "vk", "s_1", "s_2", "s_3"]),
            (["pressao dinamica", "q"], ["pressao dinamica", "q =", "0,613"]),
            (["fator topografico", "s1", "s_1"], ["fator topografico", "s_1"]),
            (["fator s2", "s2", "s_2", "rugosidade"], ["s_2", "rugosidade", "fator s2"]),
            (["fator s3", "s3", "s_3", "estatistico"], ["s_3", "estatistico", "fator estatistico"]),
        ]
        for question_terms, item_terms in phrase_boosts:
            if any(term in question for term in question_terms):
                for term in item_terms:
                    if term in haystack:
                        score += 1.0

        if profile.intent == "formula" and tipo == "formula":
            if re.search(r"\$\$?\s*[A-Za-z_\\{]+.*=", document):
                score += 0.8
            if "descricao:" in _normalize_text(document):
                score += 0.3

        if any(term in question for term in ["pressao dinamica", "pressao dinamica q", "formula da pressao", "formula de q"]):
            if re.search(r"q\s*=\s*0[,\.]613\s*\\?V_?\{?k\}?\^?2", haystack):
                score += 6.0
            if "q = 0,613" in haystack and "v_k" in haystack:
                score += 5.0
            if "q(z)" in haystack or "overline" in haystack or "flutuante" in haystack:
                score -= 2.0

        if "velocidade caracteristica" in question and tipo == "formula":
            if "v_k = v_0" in haystack or "vk = v0" in haystack:
                score += 5.0

        if any(term in question for term in ["pressao interna", "coeficiente de pressao interna", "cpi", "c pi"]):
            if "c_{pi}" in haystack or "cpi" in haystack:
                score += 4.0
            if "abertura" in haystack or "permeabilidade" in haystack:
                score += 2.5
            if "pressao efetiva interna" in haystack or "delta p_i" in haystack:
                score += 2.5

        if any(term in question for term in ["pressao externa", "coeficiente de pressao externa", "cpe", "c pe"]):
            if "c_{pe}" in haystack or "cpe" in haystack:
                score += 4.0
            if "pressao efetiva externa" in haystack or "delta p_e" in haystack:
                score += 2.5

        if "coeficiente de forma" in question:
            if "coeficiente de forma" in haystack or "c_e" in haystack or "c_i" in haystack:
                score += 4.0

        return score

    def build_context(
        self,
        retrieved: list[dict],
        pergunta: str = "",
        profile: QueryProfile | None = None,
    ) -> str:
        profile = profile or _build_query_profile(pergunta, self.fetch_k)
        blocks = []
        used_chars = 0
        guidance = guidance_for_question(profile.intent, pergunta)
        if guidance:
            blocks.append(f"[guia] Fonte: mapa normativo interno; tipo: orientacao; secao: fluxo principal\n{guidance}")
            used_chars += len(blocks[-1])
        for idx, item in enumerate(retrieved, start=1):
            metadata = item["metadata"] or {}
            fonte = metadata.get("fonte", "fonte desconhecida")
            pagina = metadata.get("pagina", "")
            tipo = metadata.get("tipo_conteudo", "")
            secao = _infer_section_from_document(item["documento"], pergunta, metadata.get("secao", ""))
            titulo = metadata.get("titulo", "")
            distance = item.get("distancia")

            document = item["documento"]
            max_doc_chars = min(self.max_doc_chars, profile.max_doc_chars)
            if len(document) > max_doc_chars:
                document = document[:max_doc_chars].rstrip() + "\n[trecho truncado]"

            header = (
                f"[{idx}] Fonte: {fonte}; pagina: {pagina}; tipo: {tipo}; "
                f"secao: {secao}; titulo: {titulo}; distancia: {distance}"
            )
            block = f"{header}\n{document}"
            context_max_chars = min(self.context_max_chars, profile.context_max_chars)
            if used_chars + len(block) > context_max_chars:
                break
            used_chars += len(block)
            blocks.append(block)

        return "\n\n---\n\n".join(blocks)

    def build_response_request(
        self,
        pergunta: str,
        previous_response_id: str | None = None,
        conversation_context: str = "",
        request_metadata: dict | None = None,
    ) -> tuple[dict, dict]:
        profile = _build_query_profile(pergunta, self.fetch_k)
        plan = self.orchestrator.plan(pergunta)
        base_params = {
            "model": self.model_name,
            "store": True,
            "reasoning": {"effort": os.getenv("OPENAI_REASONING_EFFORT", "minimal")},
        }
        if request_metadata:
            base_params["metadata"] = request_metadata
        prompt_cache_retention = os.getenv("OPENAI_PROMPT_CACHE_RETENTION", "").strip()
        if prompt_cache_retention:
            base_params["prompt_cache_retention"] = prompt_cache_retention
        if previous_response_id:
            base_params["previous_response_id"] = previous_response_id

        context_block = ""
        if conversation_context.strip():
            context_block = (
                "CONTEXTO DE CONTINUIDADE DA CONVERSA:\n"
                f"{conversation_context.strip()}"
            )

        v0_lookup = self.v0_lookup_service.lookup(pergunta)
        if v0_lookup.handled:
            prompt = f"""
TIPO DE TAREFA:
consulta_v0

REGRAS ESPECIFICAS:
- Use o resultado da ferramenta como fonte principal.
- Se houver valor de V0, explique de forma natural que ele vem do mapa de isopletas da NBR 6123.
- Explique brevemente como V0 entra no calculo da velocidade caracteristica.
- Nao invente valores adicionais.

RESULTADO DE FERRAMENTA TECNICA:
{v0_lookup.data}

RESPOSTA BASE:
{v0_lookup.markdown}

PERGUNTA DO USUARIO:
{pergunta}

{context_block}
""".strip()
            return {
                **base_params,
                "instructions": RAG_SYSTEM_INSTRUCTION,
                "input": prompt,
                "max_output_tokens": 700,
                "prompt_cache_key": "ag_ventos_v0_v1",
            }, {
                "modo": "consulta_v0",
                "modelo": self.model_name,
                "fontes": v0_lookup.fontes,
                "trechos_recuperados": [],
                "v0_lookup": v0_lookup.data,
                "orquestracao": plan.to_dict(),
            }

        if profile.intent == "calculo":
            calculation = self.calculation_engine.evaluate(pergunta)
            if calculation.handled:
                calculation_payload = {
                    "operation": calculation.operation,
                    "markdown_deterministico": calculation.markdown,
                    "missing": calculation.missing,
                    "values": calculation.values,
                    "sources": calculation.sources,
                }
                prompt = f"""
TIPO DE TAREFA:
calculo

{build_calculation_prompt(pergunta, calculation_payload)}

{context_block}
""".strip()
                return {
                    **base_params,
                    "instructions": CALCULATION_SYSTEM_INSTRUCTION,
                    "input": prompt,
                    "max_output_tokens": 900 if not calculation.missing else 450,
                    "prompt_cache_key": "ag_ventos_calc_v1",
                }, {
                    "modo": calculation.operation or "calculo",
                    "modelo": f"motor_calculo_python+{self.model_name}",
                    "fontes": calculation.sources,
                    "trechos_recuperados": [],
                    "calculo": {
                        "operation": calculation.operation,
                        "missing": calculation.missing,
                        "values": calculation.values,
                    },
                    "orquestracao": plan.to_dict(),
                }

        retrieved = self.retrieve(pergunta)
        if not retrieved:
            prompt = f"""
TIPO DE TAREFA:
sem_contexto_suficiente

PERGUNTA DO USUARIO:
{pergunta}

TAREFA:
Diga que nao encontrou informacoes suficientes na base tecnica disponivel para
responder com seguranca.

{context_block}
""".strip()
            return {
                **base_params,
                "instructions": RAG_SYSTEM_INSTRUCTION,
                "input": prompt,
                "max_output_tokens": 350,
                "prompt_cache_key": "ag_ventos_rag_v1",
            }, {
                "modo": profile.intent,
                "modelo": self.model_name,
                "fontes": [],
                "trechos_recuperados": [],
                "orquestracao": plan.to_dict(),
            }

        contexto = self.build_context(retrieved, pergunta=pergunta, profile=profile)
        prompt = f"""
TIPO DE TAREFA:
rag_normativo

{build_rag_user_prompt(contexto=contexto, pergunta=pergunta, modo=profile.intent, estrito=profile.strict)}

{context_block}
""".strip()

        fontes = self.build_sources(retrieved, pergunta, profile)

        return {
            **base_params,
            "instructions": RAG_SYSTEM_INSTRUCTION,
            "input": prompt,
            "max_output_tokens": min(self.max_output_tokens, profile.max_output_tokens),
            "prompt_cache_key": "ag_ventos_rag_v1",
        }, {
            "modo": profile.intent,
            "modelo": self.model_name,
            "fontes": fontes,
            "trechos_recuperados": retrieved,
            "orquestracao": plan.to_dict(),
        }

    def _create_response_with_retry(self, request_params: dict) -> Any:
        response = self.openai_client.responses.create(**request_params)

        incomplete = getattr(response, "status", None) == "incomplete"
        incomplete_details = getattr(response, "incomplete_details", None)
        incomplete_reason = getattr(incomplete_details, "reason", "") if incomplete_details else ""
        if incomplete and incomplete_reason == "max_output_tokens":
            retry_params = {
                **request_params,
                "max_output_tokens": max(int(request_params.get("max_output_tokens", 900)) * 2, 1800),
            }
            response = self.openai_client.responses.create(**retry_params)

        return response

    def answer(
        self,
        pergunta: str,
        previous_response_id: str | None = None,
        conversation_context: str = "",
        request_metadata: dict | None = None,
    ) -> dict:
        if previous_response_id or conversation_context.strip():
            request_params, metadata = self.build_response_request(
                pergunta=pergunta,
                previous_response_id=previous_response_id,
                conversation_context=conversation_context,
                request_metadata=request_metadata,
            )
            response = self._create_response_with_retry(request_params)
            usage = getattr(response, "usage", None)
            return {
                "resposta_markdown": response.output_text,
                "response_id": getattr(response, "id", None),
                "previous_response_id": previous_response_id,
                "uso": usage.model_dump() if usage else None,
                **metadata,
            }

        profile = _build_query_profile(pergunta, self.fetch_k)
        plan = self.orchestrator.plan(pergunta)

        v0_lookup = self.v0_lookup_service.lookup(pergunta)
        if v0_lookup.handled:
            return {
                "resposta_markdown": v0_lookup.markdown,
                "fontes": v0_lookup.fontes,
                "trechos_recuperados": [],
                "modelo": "ferramenta_v0_isopletas",
                "modo": "consulta_v0",
                "v0_lookup": v0_lookup.data,
                "orquestracao": plan.to_dict(),
                "uso": {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                },
            }

        if profile.intent == "calculo":
            calculation = self.calculation_engine.evaluate(pergunta)
            if calculation.handled:
                response_text = calculation.markdown
                usage = {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                }
                use_llm_for_calculation = os.getenv("RAG_CALCULATION_LLM_RESPONSE", "true").lower() != "false"
                if use_llm_for_calculation:
                    calculation_payload = {
                        "operation": calculation.operation,
                        "markdown_deterministico": calculation.markdown,
                        "missing": calculation.missing,
                        "values": calculation.values,
                        "sources": calculation.sources,
                    }
                    try:
                        calc_response = self.openai_client.responses.create(
                            model=self.model_name,
                            instructions=CALCULATION_SYSTEM_INSTRUCTION,
                            input=build_calculation_prompt(pergunta, calculation_payload),
                            max_output_tokens=900 if not calculation.missing else 450,
                            reasoning={"effort": os.getenv("OPENAI_REASONING_EFFORT", "minimal")},
                            prompt_cache_key="ag_ventos_calc_v1",
                        )
                        response_text = calc_response.output_text or calculation.markdown
                        usage = getattr(calc_response, "usage", None).model_dump() if getattr(calc_response, "usage", None) else usage
                    except Exception as exc:
                        print(f"Erro ao redigir calculo com IA; usando resposta deterministica: {exc}")

                return {
                    "resposta_markdown": response_text,
                    "fontes": calculation.sources,
                    "trechos_recuperados": [],
                    "modelo": f"motor_calculo_python+{self.model_name}" if use_llm_for_calculation else "motor_calculo_python",
                    "modo": calculation.operation or "calculo",
                    "calculo": {
                        "operation": calculation.operation,
                        "missing": calculation.missing,
                        "values": calculation.values,
                    },
                    "orquestracao": plan.to_dict(),
                    "uso": usage,
                }

        retrieved = self.retrieve(pergunta)
        if not retrieved:
            return {
                "resposta_markdown": "Nao encontrei informacoes suficientes na base de conhecimento para responder.",
                "fontes": [],
                "trechos_recuperados": [],
                "orquestracao": plan.to_dict(),
            }

        contexto = self.build_context(retrieved, pergunta=pergunta, profile=profile)
        prompt = build_rag_user_prompt(
            contexto=contexto,
            pergunta=pergunta,
            modo=profile.intent,
            estrito=profile.strict,
        )

        max_output_tokens = min(self.max_output_tokens, profile.max_output_tokens)
        response = self._create_response_with_retry({
            "model": self.model_name,
            "instructions": RAG_SYSTEM_INSTRUCTION,
            "input": prompt,
            "max_output_tokens": max_output_tokens,
            "reasoning": {"effort": os.getenv("OPENAI_REASONING_EFFORT", "minimal")},
            "prompt_cache_key": "ag_ventos_rag_v1",
        })

        fontes = self.build_sources(retrieved, pergunta, profile)

        return {
            "resposta_markdown": response.output_text,
            "response_id": getattr(response, "id", None),
            "fontes": fontes,
            "trechos_recuperados": retrieved,
            "modelo": self.model_name,
            "modo": profile.intent,
            "orquestracao": plan.to_dict(),
            "uso": getattr(response, "usage", None).model_dump() if getattr(response, "usage", None) else None,
        }
