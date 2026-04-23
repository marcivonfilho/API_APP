import re
from dataclasses import dataclass

from app.rag.query_expansion import normalize_text


@dataclass(frozen=True)
class TechnicalIntent:
    name: str
    confidence: float
    reasons: tuple[str, ...] = ()


AMBIGUOUS_CHOICE_PATTERNS = [
    r"\bqual\b.*\b(mais importante|principal|melhor|certo|correto|adequado)\b",
    r"\b(o que|qual)\b.*\b(devo|preciso)\b.*\b(usar|aplicar|considerar|calcular)\b",
    r"\bpor onde\b.*\b(comeco|começar|inicio|iniciar)\b",
    r"\bprimeiro\b.*\b(calculo|calcular|uso|usar|aplico|aplicar)\b",
    r"\bqual\b.*\b(fator|formula|etapa)\b.*\b(primeiro|principal)\b",
]

PROCEDURE_PATTERNS = [
    r"\bcomo\b.*\b(calculo|calcular|determino|determinar|obtenho|obter|aplico|aplicar)\b",
    r"\bpasso a passo\b",
    r"\bprocedimento\b",
    r"\bsequencia\b.*\b(calculo|norma|nbr)\b",
    r"\bfluxo\b.*\b(calculo|norma|nbr)\b",
]

SELECTION_PATTERNS = [
    r"\bqual\b.*\b(coeficiente|fator|tabela|figura|categoria|classe|grupo)\b.*\b(usar|aplicar|adotar|considerar)\b",
    r"\b(coeficiente|fator)\b.*\b(usar|aplicar|adotar|escolher)\b",
    r"\bdepende\b.*\b(de que|do que)\b",
]

COMPARISON_PATTERNS = [
    r"\b(compare|comparar|comparacao|comparação|diferenca|diferença|versus|vs)\b",
    r"\bqual\b.*\b(diferenca|diferença)\b",
]


def _matches_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def classify_technical_intent(question: str) -> TechnicalIntent:
    """Classify natural engineering questions before retrieval.

    This is intentionally generic. It detects the user's objective, not a
    specific sentence. The RAG layer still retrieves the supporting sources.
    """
    text = normalize_text(question)
    reasons: list[str] = []

    if _matches_any(text, COMPARISON_PATTERNS):
        reasons.append("comparative wording")
        return TechnicalIntent("comparacao", 0.9, tuple(reasons))

    if _matches_any(text, SELECTION_PATTERNS):
        reasons.append("normative selection")
        return TechnicalIntent("selecao_normativa", 0.9, tuple(reasons))

    if _matches_any(text, AMBIGUOUS_CHOICE_PATTERNS):
        reasons.append("ambiguous choice or priority")
        return TechnicalIntent("orientacao_normativa", 0.95, tuple(reasons))

    if _matches_any(text, PROCEDURE_PATTERNS):
        reasons.append("procedure request")
        return TechnicalIntent("procedimento", 0.85, tuple(reasons))

    if re.search(r"\b(tenho|vou projetar|estou calculando)\b", text) and re.search(
        r"\b(edificacao|estrutura|galpao|cobertura|parede|vento)\b", text
    ):
        reasons.append("project guidance")
        return TechnicalIntent("orientacao_normativa", 0.8, tuple(reasons))

    return TechnicalIntent("desconhecida", 0.0, ())
