import re
import unicodedata


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return ascii_text.lower()


TECHNICAL_EXPANSIONS: dict[str, list[str]] = {
    "velocidade basica": ["v0", "v_0", "velocidade basica do vento", "isopletas"],
    "velocidade caracteristica": ["vk", "v_k", "velocidade caracteristica do vento"],
    "pressao dinamica": ["q", "pressao dinamica do vento", "0,613", "v_k"],
    "pressao interna": [
        "pressao interna",
        "coeficiente de pressao interna",
        "cpi",
        "c_{pi}",
        "delta p_i",
        "aberturas",
        "permeabilidade",
    ],
    "pressao externa": [
        "pressao externa",
        "coeficiente de pressao externa",
        "cpe",
        "c_{pe}",
        "delta p_e",
    ],
    "coeficiente de pressao": ["cpe", "c_{pe}", "cpi", "c_{pi}", "pressao interna", "pressao externa"],
    "coeficiente de forma": ["ce", "ci", "c_e", "c_i", "forca do vento"],
    "fator topografico": ["s1", "s_1", "taludes", "morros", "vales profundos"],
    "fator s1": ["s1", "s_1", "fator topografico"],
    "fator s2": ["s2", "s_2", "rugosidade", "categoria", "classe", "altura sobre o terreno"],
    "fator s3": ["s3", "s_3", "fator estatistico", "grupo", "vida util"],
    "rugosidade": ["categoria de rugosidade", "s2", "s_2", "terreno"],
    "abertura dominante": ["abertura dominante", "pressao interna", "cpi", "permeabilidade"],
    "permeabilidade": ["permeabilidade", "aberturas", "pressao interna", "cpi"],
}


SYMBOL_EXPANSIONS: dict[str, list[str]] = {
    "v0": ["v_0", "velocidade basica", "velocidade basica do vento"],
    "vk": ["v_k", "velocidade caracteristica", "velocidade caracteristica do vento"],
    "s1": ["s_1", "fator topografico"],
    "s2": ["s_2", "rugosidade", "categoria", "classe"],
    "s3": ["s_3", "fator estatistico", "grupo"],
    "cpi": ["c_{pi}", "coeficiente de pressao interna", "pressao interna"],
    "cpe": ["c_{pe}", "coeficiente de pressao externa", "pressao externa"],
    "q": ["pressao dinamica", "q = 0,613", "v_k"],
}


STOPWORDS = {
    "que",
    "qual",
    "quais",
    "como",
    "para",
    "pela",
    "pelo",
    "uma",
    "uns",
    "das",
    "dos",
    "com",
    "sobre",
    "isso",
    "esses",
    "essa",
    "esse",
    "norma",
    "nbr",
    "vento",
    "ventos",
}


def expand_query_terms(question: str) -> list[str]:
    normalized = normalize_text(question)
    terms: list[str] = []

    def add(term: str) -> None:
        term = normalize_text(term).strip()
        if term and term not in terms:
            terms.append(term)

    add(normalized)

    for key, expansions in TECHNICAL_EXPANSIONS.items():
        if key in normalized:
            add(key)
            for expansion in expansions:
                add(expansion)

    symbols = set(re.findall(r"\b[a-z][a-z0-9_]{0,4}\b", normalized))
    for symbol in symbols:
        if symbol in SYMBOL_EXPANSIONS:
            add(symbol)
            for expansion in SYMBOL_EXPANSIONS[symbol]:
                add(expansion)

    tokens = [
        token for token in re.findall(r"[a-z0-9_]{2,}", normalized)
        if token not in STOPWORDS
    ]
    for token in tokens:
        add(token)

    return terms


def is_short_normative_query(question: str) -> bool:
    normalized = normalize_text(question)
    tokens = [token for token in re.findall(r"[a-z0-9_]{2,}", normalized) if token not in STOPWORDS]
    asks_definition = bool(re.search(r"\b(o que e|defina|definicao|explique|conceito|me fale|fale sobre|fale da|fale do)\b", normalized))
    has_known_term = any(key in normalized for key in TECHNICAL_EXPANSIONS)
    has_symbol = any(symbol in normalized.split() for symbol in SYMBOL_EXPANSIONS)
    return asks_definition and (has_known_term or has_symbol or len(tokens) <= 4)


def preferred_content_types(question: str) -> set[str]:
    normalized = normalize_text(question)
    types = {"texto"}
    formula_terms = [
        "formula",
        "equacao",
        "velocidade caracteristica",
        "pressao dinamica",
        "pressao interna",
        "pressao externa",
        "coeficiente",
        "s1",
        "s2",
        "s3",
        "v0",
        "vk",
        "q",
        "cpi",
        "cpe",
    ]
    table_terms = ["tabela", "valor", "categoria", "classe", "grupo", "coeficiente"]
    figure_terms = ["figura", "grafico", "mapa", "isopleta", "curva"]

    if any(term in normalized for term in formula_terms):
        types.add("formula")
    if any(term in normalized for term in table_terms):
        types.add("tabela")
    if any(term in normalized for term in figure_terms):
        types.add("figura")
    return types
