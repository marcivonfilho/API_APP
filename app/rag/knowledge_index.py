import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.rag.query_expansion import expand_query_terms, normalize_text


@dataclass(frozen=True)
class IndexedDocument:
    id: str
    document: str
    metadata: dict[str, Any]
    collection: str
    searchable: str


class KnowledgeIndex:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.documents: list[IndexedDocument] = []
        self._load_norma()
        self._load_artigos()

    def _load_jsonl(self, path: Path, collection: str) -> None:
        if not path.exists():
            return
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            document = item.get("document") or ""
            metadata = item.get("metadata") or {}
            metadata_text = " ".join(
                str(metadata.get(key, ""))
                for key in ["fonte", "secao", "titulo", "tipo_conteudo", "tipo_documento", "pagina"]
            )
            self.documents.append(IndexedDocument(
                id=str(item.get("id") or len(self.documents)),
                document=document,
                metadata=metadata,
                collection=collection,
                searchable=normalize_text(f"{metadata_text}\n{document}"),
            ))

    def _load_norma(self) -> None:
        norma_dir = self.base_dir / "knowledge_base" / "processado" / "norma"
        self._load_jsonl(norma_dir / "documentos.jsonl", "norma")

    def _load_artigos(self) -> None:
        artigos_dir = self.base_dir / "knowledge_base" / "processado" / "artigos"
        self._load_jsonl(artigos_dir / "documentos.jsonl", "artigos")

    def search(
        self,
        query: str,
        limit: int = 12,
        collections: set[str] | None = None,
        content_types: set[str] | None = None,
    ) -> list[dict]:
        expanded_terms = expand_query_terms(query)
        query_tokens = self._tokens(normalize_text(query))
        scored: list[tuple[float, IndexedDocument]] = []

        for doc in self.documents:
            if collections and doc.collection not in collections:
                continue
            tipo = str(doc.metadata.get("tipo_conteudo") or "")
            if content_types and tipo not in content_types:
                continue

            score = self._score(doc, expanded_terms, query_tokens)
            if score <= 0:
                continue
            scored.append((score, doc))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            {
                "documento": doc.document,
                "metadata": doc.metadata,
                "distancia": max(0.0, 1.0 / (1.0 + score)),
                "colecao": doc.collection,
                "origem_busca": "lexical",
                "lexical_score": score,
            }
            for score, doc in scored[:limit]
        ]

    def related_by_page(
        self,
        item: dict,
        limit: int = 4,
        content_types: set[str] | None = None,
    ) -> list[dict]:
        metadata = item.get("metadata") or {}
        pagina = str(metadata.get("pagina") or "")
        collection = item.get("colecao") or "norma"
        if not pagina:
            return []

        related: list[dict] = []
        for doc in self.documents:
            if doc.collection != collection:
                continue
            if str(doc.metadata.get("pagina") or "") != pagina:
                continue
            tipo = str(doc.metadata.get("tipo_conteudo") or "")
            if content_types and tipo not in content_types:
                continue
            key = (
                doc.metadata.get("fonte"),
                doc.metadata.get("pagina"),
                doc.metadata.get("secao"),
                doc.metadata.get("tipo_conteudo"),
                doc.metadata.get("formula_id") or doc.metadata.get("titulo") or doc.id,
            )
            item_key = (
                metadata.get("fonte"),
                metadata.get("pagina"),
                metadata.get("secao"),
                metadata.get("tipo_conteudo"),
                metadata.get("formula_id") or metadata.get("titulo") or "",
            )
            if key == item_key:
                continue
            related.append({
                "documento": doc.document,
                "metadata": doc.metadata,
                "distancia": 0.35,
                "colecao": doc.collection,
                "origem_busca": "related_page",
                "lexical_score": 0.0,
            })
            if len(related) >= limit:
                break
        return related

    def _score(
        self,
        doc: IndexedDocument,
        expanded_terms: list[str],
        query_tokens: set[str],
    ) -> float:
        haystack = doc.searchable
        score = 0.0

        for position, term in enumerate(expanded_terms):
            if not term:
                continue
            weight = 5.0 if position == 0 else 3.0
            if term in haystack:
                score += weight
                score += min(2.0, haystack.count(term) * 0.25)

        if query_tokens:
            matched_tokens = sum(1 for token in query_tokens if token in haystack)
            coverage = matched_tokens / max(len(query_tokens), 1)
            score += coverage * 4.0
            if coverage == 1:
                score += 2.0

        tipo = str(doc.metadata.get("tipo_conteudo") or "")
        title = normalize_text(str(doc.metadata.get("titulo") or ""))
        secao = normalize_text(str(doc.metadata.get("secao") or ""))
        source_boost = {
            "texto": 0.8,
            "formula": 0.7,
            "tabela": 0.45,
            "figura": 0.2,
        }.get(tipo, 0.0)
        score += source_boost

        for token in query_tokens:
            if token and (token in title or token in secao):
                score += 1.5

        score += self._symbol_boost(haystack, tipo, query_tokens, expanded_terms)

        return score if math.isfinite(score) else 0.0

    def _symbol_boost(
        self,
        haystack: str,
        tipo: str,
        query_tokens: set[str],
        expanded_terms: list[str],
    ) -> float:
        query_text = " ".join(expanded_terms)
        boost = 0.0
        asks_q = "pressao dinamica" in query_text or " q" in f" {' '.join(query_tokens)}"
        asks_vk = "velocidade caracteristica" in query_text or "vk" in query_tokens or "v_k" in query_tokens
        asks_s3 = "fator estatistico" in query_text or "s3" in query_tokens or "s_3" in query_tokens
        asks_s2 = "fator s2" in query_text or "rugosidade" in query_text or "s2" in query_tokens or "s_2" in query_tokens

        if asks_q and "pressao dinamica" in haystack and "q = 0,613" in haystack:
            boost += 4.0
        if asks_q and "q = 0,613" in haystack and "v_k" in haystack:
            boost += 5.0
        if asks_q and "q = 0,613 v_k^2" in haystack:
            boost += 8.0
        if asks_q and "overline" in haystack:
            boost -= 5.0
        if asks_vk and "velocidade caracteristica" in haystack and "v_k = v_0" in haystack:
            boost += 5.0
        if asks_s3 and "fator estatistico" in haystack and ("s_3" in haystack or "s3" in haystack):
            boost += 4.0
        if asks_s3 and "valores minimos do fator estatistico" in haystack:
            boost += 5.0
        if asks_s2 and ("fator s_2" in haystack or "fator $s_2" in haystack):
            boost += 2.0
        if tipo == "formula" and "=" in haystack:
            boost += 1.0
        return boost

    def _tokens(self, value: str) -> set[str]:
        return {
            token for token in re.findall(r"[a-z0-9_]{2,}", value)
            if token not in {"que", "qual", "como", "para", "vento", "norma", "nbr"}
        }
