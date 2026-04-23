from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from app.rag.query_expansion import normalize_text


@dataclass(frozen=True)
class SelectionTarget:
    name: str
    label: str
    summary: str
    required_data: tuple[str, ...]
    search_terms: tuple[str, ...]
    sources_hint: tuple[str, ...] = ()
    response_hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SelectionGuidance:
    detected: bool
    target: SelectionTarget | None = None
    confidence: float = 0.0
    reasons: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "detected": self.detected,
            "target": self.target.to_dict() if self.target else None,
            "confidence": self.confidence,
            "reasons": list(self.reasons),
        }

    def context_block(self) -> str:
        if not self.detected or not self.target:
            return ""
        required = "\n".join(f"- {item}" for item in self.target.required_data)
        sources = "\n".join(f"- {item}" for item in self.target.sources_hint)
        sources_text = f"\nFontes/secoes provaveis:\n{sources}" if sources else ""
        return f"""
POLITICA DE SELECAO NORMATIVA

Alvo identificado: {self.target.label}

Orientacao:
{self.target.summary}

Dados minimos para escolher/adotar com seguranca:
{required}
{sources_text}

Regra de resposta:
{self.target.response_hint or "Nao adote valor sem os dados do caso. Explique a dependencia e peça apenas os dados faltantes."}
""".strip()


SELECTION_TARGETS: dict[str, SelectionTarget] = {
    "coeficiente_pressao_interna": SelectionTarget(
        name="coeficiente_pressao_interna",
        label="coeficiente de pressao interna $c_{pi}$",
        summary=(
            "O coeficiente de pressao interna nao e um valor unico. Ele depende da "
            "permeabilidade, aberturas, forro/cobertura e configuracao da edificacao."
        ),
        required_data=(
            "se ha forro e se ele e estanque ou permeavel",
            "quais faces possuem aberturas e a configuracao dessas aberturas",
            "se existe abertura dominante",
            "se ha aberturas na cobertura",
            "objetivo do calculo: paredes, cobertura, elementos ou envoltoria",
        ),
        search_terms=(
            "coeficiente pressao interna cpi aberturas permeabilidade",
            "pressao interna abertura dominante forro cobertura",
            "balanco de vazoes pressao interna cpi",
        ),
        sources_hint=("NBR 6123 secao 6.3.2", "NBR 6123 secao 6.4"),
        response_hint=(
            "Diga que $c_{pi}$ depende das aberturas/permeabilidade. Peca os dados faltantes "
            "em uma lista curta e nao use linguagem interna como contexto recuperado."
        ),
    ),
    "coeficiente_pressao_externa": SelectionTarget(
        name="coeficiente_pressao_externa",
        label="coeficiente de pressao externa $c_{pe}$",
        summary=(
            "O coeficiente de pressao externa depende da geometria da edificacao, tipo de "
            "superficie, zonas/faixas, direcao do vento e relacoes dimensionais."
        ),
        required_data=(
            "tipo de superficie: parede, cobertura, platibanda, cupula ou outro elemento",
            "geometria e dimensoes relevantes da edificacao",
            "direcao do vento considerada",
            "zona/faixa da superficie onde a pressao sera aplicada",
            "inclinacao da cobertura quando aplicavel",
        ),
        search_terms=(
            "coeficiente pressao externa cpe paredes cobertura zonas",
            "tabelas coeficientes pressao externa geometria vento",
        ),
        sources_hint=("NBR 6123 capitulo 6",),
    ),
    "coeficiente_forma_forca": SelectionTarget(
        name="coeficiente_forma_forca",
        label="coeficiente de forma/forca",
        summary=(
            "Coeficientes de forma ou forca dependem do elemento estrutural, area de referencia, "
            "geometria e objetivo do calculo."
        ),
        required_data=(
            "qual elemento sera calculado",
            "area de referencia",
            "geometria/dimensoes do elemento",
            "se o objetivo e forca global ou pressao local",
        ),
        search_terms=(
            "coeficiente forma forca area referencia",
            "forca vento F q C A coeficiente aerodinamico",
        ),
        sources_hint=("NBR 6123 secoes iniciais de forca/pressao",),
    ),
    "fator_s1": SelectionTarget(
        name="fator_s1",
        label="fator topografico $S_1$",
        summary="O fator $S_1$ depende das condicoes topograficas do terreno.",
        required_data=(
            "tipo de topografia: plano/fracamente acidentado, talude, morro ou vale profundo",
            "geometria topografica quando houver talude ou morro",
            "posicao da edificacao em relacao ao acidente topografico",
        ),
        search_terms=("fator topografico S1 terreno plano talude morro vale",),
        sources_hint=("NBR 6123 secao 5.2",),
    ),
    "fator_s2": SelectionTarget(
        name="fator_s2",
        label="fator $S_2$",
        summary=(
            "O fator $S_2$ depende da categoria de rugosidade, classe da edificacao/estrutura "
            "e altura $z$ acima do terreno."
        ),
        required_data=(
            "categoria de rugosidade do terreno",
            "classe da edificacao ou dimensao caracteristica",
            "altura $z$ em metros",
        ),
        search_terms=(
            "fator S2 categoria rugosidade classe altura z",
            "tabela 3 fator S2 categoria classe",
        ),
        sources_hint=("NBR 6123 secao 5.3.3", "NBR 6123 Tabela 3"),
    ),
    "fator_s3": SelectionTarget(
        name="fator_s3",
        label="fator estatistico $S_3$",
        summary="O fator $S_3$ depende do grupo da edificacao, uso e consequencia da falha.",
        required_data=(
            "tipo de edificacao ou ocupacao",
            "grupo normativo aplicavel",
            "vida util/probabilidade quando aplicavel",
        ),
        search_terms=(
            "fator estatistico S3 grupo edificacao tabela 4",
            "Tabela 4 valores minimos fator estatistico S3",
        ),
        sources_hint=("NBR 6123 Tabela 4", "Anexo B quando aplicavel"),
    ),
    "tabela_normativa": SelectionTarget(
        name="tabela_normativa",
        label="tabela normativa",
        summary=(
            "Valores tabelados dependem dos parametros de entrada da propria tabela. "
            "Sem esses parametros, nao e seguro adotar valor."
        ),
        required_data=(
            "qual grandeza deseja obter",
            "quais parametros de entrada da tabela o caso possui",
            "geometria, categoria, classe, grupo ou altura quando aplicavel",
        ),
        search_terms=("tabela valor coeficiente categoria classe grupo altura",),
    ),
    "formula_fluxo": SelectionTarget(
        name="formula_fluxo",
        label="formula ou etapa principal do procedimento",
        summary=(
            "A formula mais importante depende do objetivo. Para fluxo geral, parte-se de "
            "$V_0$, calcula-se $V_k$, depois $q$ e finalmente pressoes/forcas."
        ),
        required_data=(
            "objetivo do usuario: velocidade, pressao, forca ou selecao de coeficientes",
            "se a pergunta pede procedimento geral ou calculo de um item especifico",
        ),
        search_terms=(
            "velocidade caracteristica V_k = V_0 S_1 S_2 S_3",
            "pressao dinamica q = 0,613 V_k^2",
            "pressao efetiva cpe cpi q",
        ),
        sources_hint=("NBR 6123 secoes 3.1, 4.2 e 4.3",),
    ),
}


TARGET_PATTERNS: list[tuple[str, list[str]]] = [
    ("coeficiente_pressao_interna", [r"\b(cpi|c pi|c_?pi|pressao interna|pressao interna)\b"]),
    ("coeficiente_pressao_externa", [r"\b(cpe|c pe|c_?pe|pressao externa|pressao externa)\b"]),
    ("coeficiente_forma_forca", [r"\b(coeficiente de forma|coeficiente de forca|coeficiente de arrasto|forca global)\b"]),
    ("fator_s1", [r"\b(s1|s_1|fator topografico)\b"]),
    ("fator_s2", [r"\b(s2|s_2|rugosidade|categoria de rugosidade)\b"]),
    ("fator_s3", [r"\b(s3|s_3|fator estatistico|grupo)\b"]),
    ("tabela_normativa", [r"\b(tabela|valor tabelado|valor da tabela)\b"]),
    ("formula_fluxo", [r"\b(formula|formula principal|mais importante|primeiro|por onde comeco|por onde comecar)\b"]),
]


SELECTION_VERBS = (
    "usar",
    "aplicar",
    "adotar",
    "escolher",
    "considerar",
    "qual",
    "quando uso",
    "quando usar",
    "devo",
    "preciso",
    "indicar",
)


def detect_selection_guidance(question: str) -> SelectionGuidance:
    text = normalize_text(question)
    asks_selection = any(term in text for term in SELECTION_VERBS)
    asks_broad_priority = any(term in text for term in ["mais importante", "principal", "primeiro", "por onde comeco", "por onde comecar"])

    if not asks_selection and not asks_broad_priority:
        return SelectionGuidance(detected=False)

    for target_name, patterns in TARGET_PATTERNS:
        if any(re.search(pattern, text) for pattern in patterns):
            return SelectionGuidance(
                detected=True,
                target=SELECTION_TARGETS[target_name],
                confidence=0.9,
                reasons=("selection wording", target_name),
            )

    if "coeficiente" in text:
        return SelectionGuidance(
            detected=True,
            target=SELECTION_TARGETS["coeficiente_forma_forca"],
            confidence=0.7,
            reasons=("generic coefficient selection",),
        )

    return SelectionGuidance(
        detected=True,
        target=SELECTION_TARGETS["formula_fluxo"],
        confidence=0.65,
        reasons=("generic selection question",),
    )


def selection_search_terms(question: str) -> list[str]:
    guidance = detect_selection_guidance(question)
    if not guidance.detected or not guidance.target:
        return []
    return list(guidance.target.search_terms)


TARGET_RELEVANCE: dict[str, dict[str, object]] = {
    "coeficiente_pressao_interna": {
        "include": ("c_{pi}", "cpi", "pressao interna", "abertura", "permeabilidade", "forro", "vazoes", "c_i^"),
        "sections": ("6.3.2", "6.4", "4.3.1", "4.3.3"),
        "prefer_types": ("texto", "formula"),
        "avoid_types": ("figura", "tabela"),
    },
    "coeficiente_pressao_externa": {
        "include": ("c_{pe}", "cpe", "pressao externa", "coeficiente de pressao externa", "parede", "cobertura", "zona"),
        "sections": ("6.2", "6.3", "4.3.1", "4.3.3"),
        "prefer_types": ("texto", "tabela", "figura", "formula"),
        "avoid_types": (),
    },
    "coeficiente_forma_forca": {
        "include": ("coeficiente de forma", "coeficiente de forca", "coeficiente de arrasto", "forca", "area de referencia", "f ="),
        "sections": ("3.1", "4.1", "4.3"),
        "prefer_types": ("texto", "formula", "tabela"),
        "avoid_types": (),
    },
    "fator_s1": {
        "include": ("s_1", "s1", "fator topografico", "talude", "morro", "vale", "terreno plano"),
        "sections": ("5.2",),
        "prefer_types": ("texto", "formula", "figura"),
        "avoid_types": (),
    },
    "fator_s2": {
        "include": ("s_2", "s2", "rugosidade", "categoria", "classe", "altura", "tabela 3"),
        "sections": ("5.3", "5.4", "A.1"),
        "prefer_types": ("texto", "tabela", "formula"),
        "avoid_types": (),
    },
    "fator_s3": {
        "include": ("s_3", "s3", "fator estatistico", "grupo", "vida util", "tabela 4"),
        "sections": ("5.5", "Anexo B", "B"),
        "prefer_types": ("texto", "tabela"),
        "avoid_types": (),
    },
    "tabela_normativa": {
        "include": ("tabela", "valor", "categoria", "classe", "grupo", "coeficiente"),
        "sections": (),
        "prefer_types": ("tabela", "texto"),
        "avoid_types": (),
    },
    "formula_fluxo": {
        "include": ("v_k", "v_0", "s_1", "s_2", "s_3", "q = 0,613", "c_{pe}", "c_{pi}", "forca"),
        "sections": ("3.1", "4.2", "4.3", "4.1"),
        "prefer_types": ("formula", "texto"),
        "avoid_types": ("figura",),
    },
}


def selection_target_name(question: str) -> str:
    guidance = detect_selection_guidance(question)
    if not guidance.detected or not guidance.target:
        return ""
    return guidance.target.name


def selection_relevance_score(question: str, document: str, metadata: dict[str, Any]) -> float:
    target_name = selection_target_name(question)
    if not target_name:
        return 0.0

    rules = TARGET_RELEVANCE.get(target_name, {})
    haystack = normalize_text(" ".join([
        document or "",
        str(metadata.get("titulo") or ""),
        str(metadata.get("secao") or ""),
        str(metadata.get("tipo_conteudo") or ""),
    ]))
    tipo = str(metadata.get("tipo_conteudo") or "")
    secao = str(metadata.get("secao") or "")

    score = 0.0
    for term in rules.get("include", ()):
        if normalize_text(str(term)) in haystack:
            score += 1.6

    for section in rules.get("sections", ()):
        if str(section) and str(secao).startswith(str(section)):
            score += 2.2

    if tipo in rules.get("prefer_types", ()):
        score += 0.8
    if tipo in rules.get("avoid_types", ()):
        score -= 1.8

    return score


def is_selection_source_relevant(question: str, document: str, metadata: dict[str, Any]) -> bool:
    target_name = selection_target_name(question)
    if not target_name:
        return True
    return selection_relevance_score(question, document, metadata) > 0.0

