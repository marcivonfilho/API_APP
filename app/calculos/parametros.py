import re
import unicodedata
from typing import Any


NUMBER = r"[-+]?\d+(?:[,.]\d+)?"


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return ascii_text.lower()


def parse_number(value: str) -> float:
    return float(value.replace(",", "."))


def _find_labeled_number(text: str, labels: list[str]) -> float | None:
    for label in labels:
        pattern = rf"(?<![a-z0-9]){label}\s*(?:=|:)?\s*({NUMBER})"
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return parse_number(match.group(1))
    return None


def _find_area(text: str) -> float | None:
    patterns = [
        rf"\bA\s*(?:=|:)\s*({NUMBER})",
        rf"\barea\s*(?:=|:)?\s*({NUMBER})",
        rf"\bárea\s*(?:=|:)?\s*({NUMBER})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return parse_number(match.group(1))
    return None


def _find_coefficient(text: str) -> float | None:
    patterns = [
        rf"\bC\s*(?:=|:)\s*({NUMBER})",
        rf"\bcoeficiente\s*(?:=|:)?\s*({NUMBER})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return parse_number(match.group(1))
    return None


def _find_category(text: str) -> str | None:
    match = re.search(r"\bcategoria\s+(I{1,3}|IV|V|1|2|3|4|5)\b", text, flags=re.IGNORECASE)
    if not match:
        return None
    value = match.group(1).upper()
    return {
        "1": "I",
        "2": "II",
        "3": "III",
        "4": "IV",
        "5": "V",
    }.get(value, value)


def _find_class(text: str) -> str | None:
    match = re.search(r"\bclasse\s+([ABC])\b", text, flags=re.IGNORECASE)
    return match.group(1).upper() if match else None


def extract_parameters(question: str) -> dict[str, Any]:
    normalized = normalize_text(question)
    raw = question or ""
    merged = f"{raw}\n{normalized}"

    params: dict[str, Any] = {
        "v0": _find_labeled_number(merged, [r"v_?0", r"velocidade\s+basica", r"velocidade\s+básica"]),
        "vk": _find_labeled_number(merged, [r"v_?k", r"velocidade\s+caracteristica", r"velocidade\s+característica"]),
        "s1": _find_labeled_number(merged, [r"s_?1"]),
        "s2": _find_labeled_number(merged, [r"s_?2"]),
        "s3": _find_labeled_number(merged, [r"s_?3"]),
        "q": _find_labeled_number(merged, [r"\bq\b", r"pressao\s+dinamica", r"pressão\s+dinâmica"]),
        "c": _find_coefficient(merged),
        "a": _find_area(merged),
        "cpe": _find_labeled_number(merged, [r"c_?pe"]),
        "cpi": _find_labeled_number(merged, [r"c_?pi"]),
        "z": _find_labeled_number(merged, [r"\bz\b", r"altura"]),
        "categoria": _find_category(merged),
        "classe": _find_class(merged),
        "grupo": _find_labeled_number(merged, [r"grupo"]),
    }

    return {key: value for key, value in params.items() if value is not None}
