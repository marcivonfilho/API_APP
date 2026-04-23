from app.rag.query_expansion import normalize_text
from app.orchestrator.selection_policy import detect_selection_guidance, selection_search_terms


MAIN_WIND_FLOW = """
MAPA NORMATIVO DE ORIENTACAO - NBR 6123

Use este mapa apenas para orientar perguntas amplas, ambiguas ou de selecao.
Sempre confirme os detalhes nos trechos recuperados da base tecnica.

Fluxo principal de calculo das acoes do vento:
1. Definir a velocidade basica do vento, V0, pelo mapa de isopletas/local.
2. Determinar os fatores S1, S2 e S3 conforme topografia, rugosidade/dimensoes/altura e estatistica/uso.
3. Calcular a velocidade caracteristica:
   $$V_k = V_0 S_1 S_2 S_3$$
4. Calcular a pressao dinamica:
   $$q = 0,613 V_k^2$$
5. Aplicar coeficientes aerodinamicos conforme o objetivo:
   - pressao externa: coeficiente de pressao externa, cpe;
   - pressao interna: coeficiente de pressao interna, cpi;
   - pressao efetiva/resultante em superficies: relacao entre cpe, cpi e q;
   - forcas globais ou em elementos: coeficientes de forma/forca e area de referencia.

Regra de prudencia:
- Quando o usuario perguntar "qual e mais importante", "qual usar" ou "por onde comecar",
  nao escolha um unico valor absoluto sem contexto.
- Explique que a formula/fator importante depende do objetivo do usuario.
- Para procedimento geral, mostre a sequencia V0 -> S1/S2/S3 -> Vk -> q -> pressoes/forcas.
- Para selecao de coeficiente, diga qual informacao falta: superficie, geometria, cobertura,
  abertura/permeabilidade, direcao do vento, categoria/classe/grupo ou objetivo de calculo.
""".strip()


QUERY_GUIDANCE: dict[str, dict[str, object]] = {
    "orientacao_normativa": {
        "context": MAIN_WIND_FLOW,
        "search_terms": [
            "velocidade caracteristica do vento V_k = V_0 S_1 S_2 S_3",
            "pressao dinamica q = 0,613 V_k^2",
            "pressao efetiva coeficiente pressao externa interna cpe cpi",
            "forca do vento coeficiente area referencia",
        ],
    },
    "procedimento": {
        "context": MAIN_WIND_FLOW,
        "search_terms": [
            "como calcular velocidade caracteristica V_k V0 S1 S2 S3",
            "pressao dinamica q = 0,613 V_k^2",
            "coeficientes aerodinamicos pressoes forcas vento",
        ],
    },
    "selecao_normativa": {
        "context": MAIN_WIND_FLOW,
        "search_terms": [
            "coeficiente pressao externa cpe pressao interna cpi",
            "coeficiente forma forca area referencia",
            "aberturas permeabilidade pressao interna",
            "categoria classe grupo fator S2 S3",
        ],
    },
}


def guidance_for_intent(intent: str) -> str:
    item = QUERY_GUIDANCE.get(intent)
    return str(item.get("context", "")) if item else ""


def guidance_for_question(intent: str, question: str) -> str:
    parts = []
    base_guidance = guidance_for_intent(intent)
    if base_guidance:
        parts.append(base_guidance)

    selection = detect_selection_guidance(question)
    selection_block = selection.context_block()
    if selection_block:
        parts.append(selection_block)

    return "\n\n".join(parts)


def search_terms_for_intent(intent: str, question: str) -> list[str]:
    item = QUERY_GUIDANCE.get(intent)
    if not item:
        return []

    base_terms = [str(term) for term in item.get("search_terms", [])]
    normalized = normalize_text(question)

    if "coeficiente" in normalized or "pressao" in normalized:
        base_terms.extend([
            "coeficiente pressao externa cpe",
            "coeficiente pressao interna cpi",
            "delta p cpe cpi q",
        ])
    if "formula" in normalized or "calculo" in normalized or "calcular" in normalized:
        base_terms.extend([
            "V_k = V_0 S_1 S_2 S_3",
            "q = 0,613 V_k^2",
        ])
    base_terms.extend(selection_search_terms(question))

    seen = set()
    unique_terms = []
    for term in base_terms:
        key = normalize_text(term)
        if key and key not in seen:
            seen.add(key)
            unique_terms.append(term)
    return unique_terms
