import re
from dataclasses import dataclass

from app.orchestrator.selection_policy import selection_target_name
from app.rag.intents import classify_technical_intent
from app.rag.query_expansion import (
    is_short_normative_query,
    normalize_text,
    preferred_content_types,
)


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


def query_content_intents(question: str) -> set[str]:
    text = normalize_text(question)
    intents: set[str] = {"texto"}
    if re.search(r"\b(calcul|formula|equacao|pressao dinamica|forca|vk|v_k|q\b)", text):
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
    if re.search(r"\b(artigo|proposta|atualizacao|isopleta)\b", text):
        intents.add("artigo")
    for content_type in preferred_content_types(question):
        if content_type == "formula":
            intents.add("formula")
        elif content_type == "tabela":
            intents.add("tabela")
        elif content_type == "figura":
            intents.add("figura")
    return intents


def build_query_profile(question: str, default_fetch_k: int) -> QueryProfile:
    normalized = normalize_text(question)
    intents = query_content_intents(question)
    technical_intent = classify_technical_intent(question)
    strict = bool(re.search(r"\b(apenas|somente|so|sem explicacao|direto|responda curto)\b", normalized))
    is_definition = bool(re.search(r"\b(o que e|defina|definicao)\b", normalized))

    is_calc = bool(re.search(r"\b(calcule|calcular|calculo|determine|determinar)\b", normalized))
    is_table = "tabela" in intents and not is_calc
    is_formula = "formula" in intents and not is_calc
    is_figure = "figura" in intents
    is_comparison = bool(re.search(r"\b(compare|comparar|comparacao|diferen|versus|vs)\b", normalized))
    is_normative_term = is_short_normative_query(question)

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
