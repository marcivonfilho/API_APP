import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


SOURCE_NAME = "NBR 6123"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def page_key_from_name(name: str) -> str:
    match = re.match(r"pag_(.+?)_(?:teoria|raw|formula_\d+|tabela_\d+|figura)\.", name)
    if match:
        return match.group(1)
    return ""


def numeric_page(value: str | int | None) -> int | None:
    if value is None:
        return None
    match = re.fullmatch(r"\d+", str(value).strip())
    if not match:
        return None
    return int(match.group(0))


def base_metadata(page_key: str, raw_index: dict[str, dict[str, Any]]) -> dict[str, Any]:
    raw = raw_index.get(page_key) or {}
    page_printed = raw.get("numero_pagina_impresso") or page_key
    return {
        "fonte": SOURCE_NAME,
        "tipo_documento": "norma_tecnica",
        "pagina": str(page_printed),
        "pagina_key": page_key,
        "pagina_numerica": numeric_page(str(page_printed)),
        "secao": raw.get("ultima_secao_detectada") or raw.get("secao_iniciada_na_pagina") or "",
        "tipo_pagina": raw.get("tipo_pagina") or "",
    }


def is_index_or_invalid_page(page_key: str, metadata: dict[str, Any]) -> bool:
    if page_key in {"95 páginas", "sem_numero_12"}:
        return True
    if numeric_page(page_key) is None:
        return True
    return metadata.get("pagina_numerica") is None


def remove_formula_appendix(text: str) -> str:
    marker = "### Formulas extraidas nesta pagina"
    if marker in text:
        text = text.split(marker, 1)[0]
    return text.strip()


def remove_structured_table_leaks(text: str, table_titles: list[str]) -> tuple[str, bool]:
    cleaned = text
    removed = False

    for title in table_titles:
        first_line = (title or "").splitlines()[0].strip()
        if not first_line or first_line not in cleaned:
            continue

        # Remove a dense OCR table block until the next heading, paragraph with
        # normative wording, or the end of the text. This is intentionally
        # conservative: if the pattern is not clear, the text stays untouched.
        pattern = re.compile(
            rf"{re.escape(first_line)}[\s\S]*?(?=\n#|\n[A-ZÁÉÍÓÚÂÊÔÃÕÇ][^\n]{{40,}}\n|$)",
            re.MULTILINE,
        )
        new_cleaned, count = pattern.subn(
            f"[{first_line} extraida em arquivo estruturado de tabela]", cleaned, count=1
        )
        if count:
            cleaned = new_cleaned
            removed = True

    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned, removed


def clean_text_for_rag(text: str, table_titles: list[str]) -> tuple[str, list[str]]:
    notes: list[str] = []
    original = text or ""
    cleaned = remove_formula_appendix(original)
    if cleaned != original.strip():
        notes.append("formula_appendix_removed")

    cleaned, removed_table = remove_structured_table_leaks(cleaned, table_titles)
    if removed_table:
        notes.append("structured_table_leak_removed")

    return cleaned.strip(), notes


BAD_FORMULA_PATTERNS = [
    r"\bas for\b",
    r"podem ser",
    r"menor valor",
    r"massa espec",
    r"e de temperatura",
    r"^\$\$h\s*=\s*π\$\$",
    r"^\$\$i\}",
    r"^\$\$α\s*=\s*K\$\$",
    r"^\$\$dio\s*=",
    r"^\$\$atm\s*=",
    r"f_v\s*=\s*\\frac\{C\s*\}\{C\s*\}",
    r"q\s*=\s*0,613\s*V_k\^2\s*V_k",
]


def formula_rejection_reason(formula: dict[str, Any]) -> str | None:
    equation = (formula.get("equacao") or "").strip()
    section = str(formula.get("secao") or "")

    if not equation:
        return "empty_equation"
    if formula.get("status_validacao") == "suspeita":
        return "status_suspeita"
    if equation.count("(") != equation.count(")") or equation.count("{") != equation.count("}"):
        return "unbalanced_math"
    if section in {"2", "3", "6", "12", "None"}:
        return "suspicious_section"

    for pattern in BAD_FORMULA_PATTERNS:
        if re.search(pattern, equation, flags=re.IGNORECASE):
            return "known_bad_pattern"

    if len(equation) < 10:
        return "too_short"
    if len(equation) > 500:
        return "too_long"

    return None


def table_rejection_reason(table: dict[str, Any]) -> str | None:
    data = table.get("dados") or {}
    headers = data.get("headers") or []
    rows = data.get("rows") or []
    title = table.get("titulo") or ""

    if not headers or not rows:
        return "empty_table"
    if "pag_viii" in str(table.get("arquivo_origem", "")) or "Tabela " in title and not rows:
        return "index_table"

    expected = len(headers)
    if expected <= 0:
        return "missing_headers"
    if any(not isinstance(row, list) or len(row) != expected for row in rows):
        return "misaligned_rows"

    return None


def load_raw_index(raw_dir: Path) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    if not raw_dir.exists():
        return index

    for raw_path in raw_dir.glob("pag_*_raw.json"):
        page_key = page_key_from_name(raw_path.name)
        if not page_key:
            continue
        index[page_key] = read_json(raw_path)

    return index


def table_titles_by_page(tables_dir: Path) -> dict[str, list[str]]:
    titles: dict[str, list[str]] = {}
    if not tables_dir.exists():
        return titles

    for path in tables_dir.glob("pag_*_tabela_*.json"):
        page_key = page_key_from_name(path.name)
        data = read_json(path)
        title = data.get("titulo")
        if title:
            titles.setdefault(page_key, []).append(title)

    return titles


def build_text_records(extraidos_dir: Path, raw_index: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], Counter]:
    records: list[dict[str, Any]] = []
    stats: Counter = Counter()
    titles_by_page = table_titles_by_page(extraidos_dir / "tabelas")

    for path in sorted((extraidos_dir / "textos").glob("pag_*_teoria.md")):
        page_key = page_key_from_name(path.name)
        metadata = base_metadata(page_key, raw_index)
        if is_index_or_invalid_page(page_key, metadata):
            stats["text_skipped_index_or_invalid"] += 1
            continue

        raw_text = path.read_text(encoding="utf-8")
        text, notes = clean_text_for_rag(raw_text, titles_by_page.get(page_key, []))
        if len(text.strip()) < 80:
            stats["text_skipped_too_short"] += 1
            continue

        metadata.update({
            "tipo_conteudo": "texto",
            "arquivo_origem": str(path),
            "notas_processamento": notes,
        })
        records.append({
            "id": f"nbr6123:page:{page_key}:text",
            "document": text,
            "metadata": metadata,
        })
        stats["text_kept"] += 1

    return records, stats


def build_formula_records(extraidos_dir: Path, raw_index: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], Counter]:
    records: list[dict[str, Any]] = []
    stats: Counter = Counter()

    for path in sorted((extraidos_dir / "formulas").glob("pag_*_formula_*.json")):
        page_key = page_key_from_name(path.name)
        metadata = base_metadata(page_key, raw_index)
        formula = read_json(path)
        formula["arquivo_origem"] = str(path)

        reason = formula_rejection_reason(formula)
        if is_index_or_invalid_page(page_key, metadata):
            reason = reason or "index_or_invalid_page"
        if reason:
            stats[f"formula_rejected_{reason}"] += 1
            continue

        equation = formula.get("equacao") or ""
        description = formula.get("descricao") or "Formula extraida da norma"
        section = formula.get("secao") or metadata.get("secao") or ""
        content = (
            f"Formula da {SOURCE_NAME}.\n"
            f"Pagina: {metadata['pagina']}.\n"
            f"Secao: {section}.\n"
            f"Descricao: {description}\n"
            f"Equacao: {equation}"
        )

        metadata.update({
            "tipo_conteudo": "formula",
            "secao": section,
            "formula_id": formula.get("formula_id") or path.stem,
            "tipo_formula": formula.get("tipo_formula") or "",
            "origem_formula": formula.get("origem") or "",
            "arquivo_origem": str(path),
        })
        records.append({
            "id": f"nbr6123:page:{page_key}:formula:{path.stem}",
            "document": content,
            "metadata": metadata,
            "formula": formula,
        })
        stats["formula_kept"] += 1

    return records, stats


def build_table_records(extraidos_dir: Path, raw_index: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], Counter]:
    records: list[dict[str, Any]] = []
    stats: Counter = Counter()

    for path in sorted((extraidos_dir / "tabelas").glob("pag_*_tabela_*.json")):
        page_key = page_key_from_name(path.name)
        metadata = base_metadata(page_key, raw_index)
        table = read_json(path)
        table["arquivo_origem"] = str(path)

        reason = table_rejection_reason(table)
        if is_index_or_invalid_page(page_key, metadata):
            reason = reason or "index_or_invalid_page"
        if reason:
            stats[f"table_rejected_{reason}"] += 1
            continue

        title = table.get("titulo") or f"Tabela da pagina {metadata['pagina']}"
        data = table.get("dados") or {}
        content = (
            f"{title}\n"
            f"Fonte: {SOURCE_NAME}, pagina {metadata['pagina']}.\n"
            f"Secao: {metadata.get('secao') or 'nao identificada'}.\n"
            f"Dados estruturados:\n{json.dumps(data, ensure_ascii=False)}"
        )

        metadata.update({
            "tipo_conteudo": "tabela",
            "titulo": title,
            "arquivo_origem": str(path),
        })
        records.append({
            "id": f"nbr6123:page:{page_key}:table:{path.stem}",
            "document": content,
            "metadata": metadata,
            "table": table,
        })
        stats["table_kept"] += 1

    return records, stats


def build_figure_records(extraidos_dir: Path, raw_index: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], Counter]:
    records: list[dict[str, Any]] = []
    stats: Counter = Counter()

    for path in sorted((extraidos_dir / "figuras").glob("pag_*_figura.json")):
        page_key = page_key_from_name(path.name)
        metadata = base_metadata(page_key, raw_index)
        if is_index_or_invalid_page(page_key, metadata):
            stats["figure_skipped_index_or_invalid"] += 1
            continue

        figure = read_json(path)
        caption = figure.get("legenda") or figure.get("figura_legenda") or ""
        if not caption:
            stats["figure_skipped_empty"] += 1
            continue

        metadata.update({
            "tipo_conteudo": "figura",
            "arquivo_origem": str(path),
        })
        records.append({
            "id": f"nbr6123:page:{page_key}:figure",
            "document": f"Figura da {SOURCE_NAME}, pagina {metadata['pagina']}: {caption}",
            "metadata": metadata,
            "figure": figure,
        })
        stats["figure_kept"] += 1

    return records, stats


def prepare_processed_knowledge_base(
    base_dir: Path,
    output_dir: Path | None = None,
    mirror_legacy: bool = False,
) -> dict[str, Any]:
    extraidos_dir = base_dir / "knowledge_base" / "extraidos"
    output_dir = output_dir or base_dir / "knowledge_base" / "processado" / "norma"

    raw_index = load_raw_index(extraidos_dir / "raw_paginas")
    text_records, text_stats = build_text_records(extraidos_dir, raw_index)
    formula_records, formula_stats = build_formula_records(extraidos_dir, raw_index)
    table_records, table_stats = build_table_records(extraidos_dir, raw_index)
    figure_records, figure_stats = build_figure_records(extraidos_dir, raw_index)

    documents = text_records + formula_records + table_records + figure_records

    write_jsonl(output_dir / "documentos.jsonl", documents)
    write_jsonl(output_dir / "formulas.jsonl", formula_records)
    write_jsonl(output_dir / "tabelas.jsonl", table_records)
    write_jsonl(output_dir / "figuras.jsonl", figure_records)

    stats = Counter()
    stats.update(text_stats)
    stats.update(formula_stats)
    stats.update(table_stats)
    stats.update(figure_stats)

    manifest = {
        "fonte": SOURCE_NAME,
        "extraidos_dir": str(extraidos_dir),
        "output_dir": str(output_dir),
        "totais": {
            "documentos": len(documents),
            "textos": len(text_records),
            "formulas": len(formula_records),
            "tabelas": len(table_records),
            "figuras": len(figure_records),
        },
        "estatisticas": dict(sorted(stats.items())),
        "arquivos": {
            "documentos": str(output_dir / "documentos.jsonl"),
            "formulas": str(output_dir / "formulas.jsonl"),
            "tabelas": str(output_dir / "tabelas.jsonl"),
            "figuras": str(output_dir / "figuras.jsonl"),
        },
    }
    write_json(output_dir / "manifest.json", manifest)

    if mirror_legacy:
        legacy_dir = base_dir / "knowledge_base" / "processado"
        write_jsonl(legacy_dir / "documentos.jsonl", documents)
        write_jsonl(legacy_dir / "formulas.jsonl", formula_records)
        write_jsonl(legacy_dir / "tabelas.jsonl", table_records)
        write_jsonl(legacy_dir / "figuras.jsonl", figure_records)
        legacy_manifest = dict(manifest)
        legacy_manifest["output_dir"] = str(legacy_dir)
        legacy_manifest["espelho_de"] = str(output_dir)
        legacy_manifest["arquivos"] = {
            "documentos": str(legacy_dir / "documentos.jsonl"),
            "formulas": str(legacy_dir / "formulas.jsonl"),
            "tabelas": str(legacy_dir / "tabelas.jsonl"),
            "figuras": str(legacy_dir / "figuras.jsonl"),
        }
        write_json(legacy_dir / "manifest.json", legacy_manifest)

    return manifest
