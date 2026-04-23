import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from app.rag.preprocessing import write_json, write_jsonl


def stable_id(*parts: str) -> str:
    raw = "::".join(str(part) for part in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def chunk_text(text: str, max_chars: int = 1500, overlap: int = 180) -> list[str]:
    text = re.sub(r"[ \t]+", " ", text or "").strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
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
            continue
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
        step = max_chars - overlap
        while start < len(chunk):
            final_chunks.append(chunk[start:start + max_chars].strip())
            start += step

    return [chunk for chunk in final_chunks if len(chunk.strip()) >= 120]


def clean_pdf_text(text: str) -> str:
    text = text or ""
    text = text.replace("\x00", "")
    text = re.sub(r"(?m)^\s*\d+\s*$", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def infer_section(text: str, page_number: int) -> str:
    first_lines = [
        line.strip() for line in (text or "").splitlines()[:12]
        if line.strip()
    ]
    joined = " ".join(first_lines).lower()

    known = [
        ("resumo", "Resumo"),
        ("abstract", "Abstract"),
        ("introdução", "Introdução"),
        ("introducao", "Introdução"),
        ("metodologia", "Metodologia"),
        ("resultados", "Resultados"),
        ("discussão", "Discussão"),
        ("discussao", "Discussão"),
        ("conclusão", "Conclusão"),
        ("conclusao", "Conclusão"),
        ("referências", "Referências"),
        ("referencias", "Referências"),
    ]
    for marker, label in known:
        if marker in joined:
            return label

    if page_number == 1:
        return "Introdução"
    return ""


def extract_pdf_pages(pdf_path: Path) -> list[dict[str, Any]]:
    try:
        import fitz
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Dependencia ausente: PyMuPDF/fitz. Instale com "
            "`python -m pip install PyMuPDF`."
        ) from exc

    doc = fitz.open(pdf_path)
    pages: list[dict[str, Any]] = []
    for page_index in range(len(doc)):
        page_number = page_index + 1
        text = clean_pdf_text(doc.load_page(page_index).get_text("text"))
        pages.append({
            "pagina": page_number,
            "texto": text,
            "secao": infer_section(text, page_number),
        })
    doc.close()
    return pages


def build_article_records(pdf_path: Path) -> tuple[list[dict[str, Any]], Counter]:
    stats: Counter = Counter()
    records: list[dict[str, Any]] = []
    source = pdf_path.stem.replace("_", " ")

    pages = extract_pdf_pages(pdf_path)
    for page in pages:
        page_number = str(page["pagina"])
        page_text = page["texto"]
        if len(page_text.strip()) < 120:
            stats["pages_skipped_too_short"] += 1
            continue

        chunks = chunk_text(page_text)
        for chunk_index, chunk in enumerate(chunks, start=1):
            metadata = {
                "fonte": source,
                "tipo_documento": "artigo",
                "tipo_fonte": "complementar",
                "forca_normativa": "nao_normativo",
                "tipo_conteudo": "texto",
                "pagina": page_number,
                "secao": page["secao"],
                "arquivo_origem": str(pdf_path),
            }
            records.append({
                "id": stable_id("artigo", pdf_path.name, page_number, str(chunk_index), chunk[:80]),
                "document": chunk,
                "metadata": metadata,
            })
            stats["chunks_kept"] += 1

    stats["pages_total"] += len(pages)
    return records, stats


def prepare_processed_articles(base_dir: Path, output_dir: Path | None = None) -> dict[str, Any]:
    artigos_dir = base_dir / "knowledge_base" / "artigos"
    output_dir = output_dir or base_dir / "knowledge_base" / "processado" / "artigos"

    documents: list[dict[str, Any]] = []
    stats: Counter = Counter()
    sources: list[dict[str, Any]] = []

    if artigos_dir.exists():
        for pdf_path in sorted(artigos_dir.glob("*.pdf")):
            article_records, article_stats = build_article_records(pdf_path)
            documents.extend(article_records)
            stats.update(article_stats)
            sources.append({
                "arquivo": str(pdf_path),
                "fonte": pdf_path.stem.replace("_", " "),
                "documentos": len(article_records),
            })

    write_jsonl(output_dir / "documentos.jsonl", documents)

    manifest = {
        "fonte": "artigos_tecnicos",
        "tipo_fonte": "complementar",
        "artigos_dir": str(artigos_dir),
        "output_dir": str(output_dir),
        "totais": {
            "documentos": len(documents),
            "artigos": len(sources),
        },
        "fontes": sources,
        "estatisticas": dict(sorted(stats.items())),
        "arquivos": {
            "documentos": str(output_dir / "documentos.jsonl"),
        },
    }
    write_json(output_dir / "manifest.json", manifest)
    return manifest
