from __future__ import annotations

import re

from app.orchestrator.selection_policy import detect_selection_guidance
from app.rag.intents import classify_technical_intent
from app.rag.query_expansion import normalize_text
from app.orchestrator.schemas import OrchestrationPlan


def build_orchestration_plan(question: str) -> OrchestrationPlan:
    text = normalize_text(question)
    technical_intent = classify_technical_intent(question)
    selection_guidance = detect_selection_guidance(question)
    reasons = list(technical_intent.reasons)

    asks_v0_location = (
        ("velocidade basica" in text or "v0" in text or "v_0" in text)
        and bool(re.search(r"\b(em|para|na|no|cidade|municipio|municipio|lat|lon|long)\b", text))
        and not any(term in text for term in ["o que e", "defina", "conceito", "segundo a norma"])
    )
    asks_calculation = bool(re.search(r"\b(calcule|calcular|calculo|determine|determinar)\b", text))
    asks_article = bool(re.search(r"\b(artigo|proposta|atualizacao|atualizacao|isopleta)\b", text))
    asks_comparison = bool(re.search(r"\b(compare|comparar|comparacao|diferenca|versus|vs)\b", text))

    if asks_v0_location:
        return OrchestrationPlan(
            intent="consulta_v0",
            confidence=0.95,
            route="tool_first",
            tools=["lookup_v0"],
            collections=["norma"],
            response_mode="consulta_localizacao",
            needs_llm=True,
            reasons=reasons + ["consulta V0 por localizacao"],
        )

    if technical_intent.name in {"orientacao_normativa", "procedimento", "selecao_normativa"} or selection_guidance.detected:
        intent_name = (
            "selecao_normativa"
            if selection_guidance.detected and technical_intent.name not in {"procedimento", "orientacao_normativa"}
            else technical_intent.name
        )
        if intent_name == "desconhecida":
            intent_name = "selecao_normativa"
        tools = ["get_normative_flow", "search_norma"]
        return OrchestrationPlan(
            intent=intent_name,
            confidence=max(technical_intent.confidence, selection_guidance.confidence),
            route="guided_rag",
            tools=tools,
            collections=["norma"],
            response_mode=intent_name,
            needs_llm=True,
            reasons=reasons + list(selection_guidance.reasons),
            warnings=["Pergunta pode depender de dados do caso; pedir apenas o que faltar."],
            selection=selection_guidance.to_dict() if selection_guidance.detected else None,
        )

    if asks_calculation:
        return OrchestrationPlan(
            intent="calculo",
            confidence=0.9,
            route="calculation_first",
            tools=["calculate_wind"],
            collections=["norma"],
            response_mode="calculo",
            needs_llm=True,
            reasons=reasons + ["pergunta de calculo"],
            warnings=["Calcular somente se houver dados suficientes."],
        )

    if asks_article and asks_comparison:
        return OrchestrationPlan(
            intent="comparacao",
            confidence=0.85,
            route="rag_multi_collection",
            tools=["search_norma", "search_articles"],
            collections=["norma", "artigos"],
            response_mode="comparativo",
            needs_llm=True,
            reasons=reasons + ["comparacao entre norma e artigo"],
        )

    if asks_article:
        return OrchestrationPlan(
            intent="artigo",
            confidence=0.8,
            route="rag_articles",
            tools=["search_articles"],
            collections=["artigos"],
            response_mode="tecnico_artigo",
            needs_llm=True,
            reasons=reasons + ["consulta a artigo tecnico"],
        )

    return OrchestrationPlan(
        intent=technical_intent.name if technical_intent.name != "desconhecida" else "rag_normativo",
        confidence=max(technical_intent.confidence, 0.5),
        route="rag_normativo",
        tools=["search_norma"],
        collections=["norma"],
        response_mode="tecnico",
        needs_llm=True,
        reasons=reasons or ["consulta normativa geral"],
    )
