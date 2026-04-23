import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from app.rag.embeddings import get_embedding_function
from app.rag.preprocessing import prepare_processed_knowledge_base


DEFAULT_COLLECTION_NAME = "conhecimento_ventos"
NORMA_COLLECTION_NAME = "nbr6123_norma"
ARTIGOS_COLLECTION_NAME = "ventos_artigos"


def stable_id(*parts: str) -> str:
    raw = "::".join(str(part) for part in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def chunk_text(text: str, max_chars: int = 1400, overlap: int = 180) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        if not current:
            current = paragraph
            continue

        if len(current) + len(paragraph) + 2 <= max_chars:
            current += "\n\n" + paragraph
        else:
            chunks.append(current)
            tail = current[-overlap:] if overlap > 0 else ""
            current = (tail + "\n\n" + paragraph).strip()

    if current:
        chunks.append(current)

    final_chunks: list[str] = []
    for chunk in chunks:
        if len(chunk) <= max_chars * 1.35:
            final_chunks.append(chunk)
            continue

        start = 0
        while start < len(chunk):
            final_chunks.append(chunk[start:start + max_chars].strip())
            start += max_chars - overlap

    return [chunk for chunk in final_chunks if chunk]


def metadata_value(value: Any) -> str | int | float | bool:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return value
    return json.dumps(value, ensure_ascii=False)


def build_page_documents(raw_path: Path) -> list[dict]:
    data = json.loads(raw_path.read_text(encoding="utf-8"))
    pagina = str(data.get("numero_pagina_impresso") or raw_path.stem)
    fonte = "NBR 6123"
    secao = data.get("ultima_secao_detectada") or data.get("secao_iniciada_na_pagina") or ""

    docs: list[dict] = []

    texto = data.get("texto_teorico") or ""
    for idx, chunk in enumerate(chunk_text(texto), start=1):
        docs.append({
            "id": stable_id("nbr6123", pagina, "texto", str(idx), chunk[:80]),
            "document": chunk,
            "metadata": {
                "fonte": fonte,
                "tipo_documento": "norma_tecnica",
                "tipo_conteudo": "texto",
                "pagina": pagina,
                "secao": secao,
                "arquivo_origem": str(raw_path),
            },
        })

    for idx, formula in enumerate(data.get("formulas") or [], start=1):
        equacao = formula.get("equacao") or ""
        descricao = formula.get("descricao") or "Formula extraida da norma"
        content = (
            f"Formula da {fonte}, pagina {pagina}.\n"
            f"Secao: {formula.get('secao') or secao or 'nao identificada'}.\n"
            f"Descricao: {descricao}\n"
            f"Equacao: {equacao}"
        )
        docs.append({
            "id": stable_id("nbr6123", pagina, "formula", str(idx), equacao),
            "document": content,
            "metadata": {
                "fonte": fonte,
                "tipo_documento": "norma_tecnica",
                "tipo_conteudo": "formula",
                "pagina": pagina,
                "secao": formula.get("secao") or secao,
                "formula_id": formula.get("formula_id") or "",
                "arquivo_origem": str(raw_path),
            },
        })

    for idx, tabela in enumerate(data.get("tabelas") or [], start=1):
        titulo = tabela.get("titulo") or f"Tabela da pagina {pagina}"
        content = (
            f"{titulo}\n"
            f"Fonte: {fonte}, pagina {pagina}.\n"
            f"Dados:\n{json.dumps(tabela.get('dados') or tabela, ensure_ascii=False, indent=2)}"
        )
        docs.append({
            "id": stable_id("nbr6123", pagina, "tabela", str(idx), titulo),
            "document": content,
            "metadata": {
                "fonte": fonte,
                "tipo_documento": "norma_tecnica",
                "tipo_conteudo": "tabela",
                "pagina": pagina,
                "secao": secao,
                "titulo": titulo,
                "arquivo_origem": str(raw_path),
            },
        })

    figura = data.get("figura_legenda")
    if figura:
        docs.append({
            "id": stable_id("nbr6123", pagina, "figura", figura),
            "document": f"Figura da {fonte}, pagina {pagina}: {figura}",
            "metadata": {
                "fonte": fonte,
                "tipo_documento": "norma_tecnica",
                "tipo_conteudo": "figura",
                "pagina": pagina,
                "secao": secao,
                "arquivo_origem": str(raw_path),
            },
        })

    return docs


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    docs: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            docs.append(json.loads(line))
    return docs


def collect_norma_documents(base_dir: Path) -> list[dict]:
    processed_path = base_dir / "knowledge_base" / "processado" / "norma" / "documentos.jsonl"
    docs = load_jsonl(processed_path)
    if docs:
        return docs

    legacy_path = base_dir / "knowledge_base" / "processado" / "documentos.jsonl"
    docs = load_jsonl(legacy_path)
    if docs:
        return [
            doc for doc in docs
            if (doc.get("metadata") or {}).get("tipo_documento") != "artigo"
        ]

    raw_dir = base_dir / "knowledge_base" / "extraidos" / "raw_paginas"
    docs: list[dict] = []
    if raw_dir.exists():
        for raw_path in sorted(raw_dir.glob("pag_*_raw.json")):
            docs.extend(build_page_documents(raw_path))
    return docs


def collect_article_documents(base_dir: Path) -> list[dict]:
    processed_path = base_dir / "knowledge_base" / "processado" / "artigos" / "documentos.jsonl"
    return load_jsonl(processed_path)


def collect_documents(base_dir: Path, target: str = "norma") -> list[dict]:
    if target == "norma":
        return collect_norma_documents(base_dir)
    if target == "artigos":
        return collect_article_documents(base_dir)
    if target == "todos":
        return collect_norma_documents(base_dir) + collect_article_documents(base_dir)
    raise ValueError("target invalido. Use 'norma', 'artigos' ou 'todos'.")


def collection_name_for_target(target: str) -> str:
    if target == "norma":
        return NORMA_COLLECTION_NAME
    if target == "artigos":
        return ARTIGOS_COLLECTION_NAME
    if target == "todos":
        return DEFAULT_COLLECTION_NAME
    raise ValueError("target invalido. Use 'norma', 'artigos' ou 'todos'.")


def ingest_knowledge_base(
    base_dir: Path,
    chroma_path: Path,
    collection_name: str | None = None,
    prepare_processed: bool = True,
    batch_size: int | None = None,
    target: str = "norma",
) -> int:
    try:
        import chromadb
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Dependencia ausente: chromadb. Instale as dependencias com "
            "`python -m pip install -r requirements.txt` e rode a ingestao novamente."
        ) from exc

    if prepare_processed:
        prepare_processed_knowledge_base(
            base_dir,
            output_dir=base_dir / "knowledge_base" / "processado" / "norma",
            mirror_legacy=True,
        )

    collection_name = collection_name or collection_name_for_target(target)

    embedding_function = get_embedding_function()
    client = chromadb.PersistentClient(path=str(chroma_path))
    collection = client.get_or_create_collection(
        name=collection_name,
        embedding_function=embedding_function,
        metadata={"hnsw:space": "cosine"},
    )

    docs = collect_documents(base_dir, target=target)
    if not docs:
        return 0

    batch_size = batch_size or int(os.getenv("RAG_INGEST_BATCH_SIZE", "80"))
    batch_size = max(1, min(batch_size, 100))

    for start in range(0, len(docs), batch_size):
        batch = docs[start:start + batch_size]
        collection.upsert(
            ids=[item["id"] for item in batch],
            documents=[item["document"] for item in batch],
            metadatas=[
                {key: metadata_value(value) for key, value in item["metadata"].items()}
                for item in batch
            ],
        )

    return len(docs)
