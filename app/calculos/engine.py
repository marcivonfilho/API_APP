from app.calculos.forcas import calcular_forca
from app.calculos.parametros import extract_parameters, normalize_text
from app.calculos.pressoes import (
    calcular_delta_p,
    calcular_pressao_externa,
    calcular_pressao_interna,
    calcular_q,
)
from app.calculos.schemas import CalculationResult
from app.calculos.tabelas_normativas import calcular_s2, buscar_s3
from app.calculos.vento_base import calcular_vk


def _fmt(value: float, decimals: int = 2) -> str:
    return f"{value:.{decimals}f}".replace(".", ",")


def _missing_result(operation: str, missing: list[str]) -> CalculationResult:
    items = "\n".join(f"- {item}" for item in missing)
    return CalculationResult(
        handled=True,
        operation=operation,
        missing=missing,
        markdown=(
            "Para executar esse cálculo com segurança, preciso dos seguintes dados:\n\n"
            f"{items}\n\n"
            "Não vou estimar valores normativos ou coeficientes sem esses dados."
        ),
    )


def _source(secao: str, pagina: str, tipo: str = "formula") -> dict[str, str]:
    return {
        "fonte": "NBR 6123",
        "pagina": pagina,
        "secao": secao,
        "tipo_conteudo": tipo,
        "colecao": "norma",
    }


class CalculationEngine:
    def evaluate(self, question: str) -> CalculationResult:
        text = normalize_text(question)
        if not any(word in text for word in ["calcule", "calcular", "calculo", "determine", "determinar"]):
            return CalculationResult(handled=False)

        params = extract_parameters(question)

        if "s2" in text and ("categoria" in text or "classe" in text or "altura" in text or " z " in f" {text} "):
            return self._handle_s2(params)

        if "s3" in text and "grupo" in text:
            return self._handle_s3(params)

        if "forca" in text or "força" in question.lower() or " f " in f" {text} ":
            return self._handle_force(params)

        if "delta p" in text or "pressao efetiva" in text or "pressão efetiva" in question.lower():
            return self._handle_delta_p(params)

        if "pressao externa" in text or "pressão externa" in question.lower():
            return self._handle_pe(params)

        if "pressao interna" in text or "pressão interna" in question.lower():
            return self._handle_pi(params)

        if " q" in f" {text}" or "pressao dinamica" in text or "pressão dinâmica" in question.lower():
            return self._handle_q(params)

        if "vk" in text or "v_k" in text or "velocidade caracteristica" in text:
            return self._handle_vk(params)

        return CalculationResult(handled=False)

    def _handle_vk(self, params: dict) -> CalculationResult:
        missing = [
            label for key, label in [
                ("v0", "$V_0$"),
                ("s1", "$S_1$"),
                ("s2", "$S_2$"),
                ("s3", "$S_3$"),
            ]
            if key not in params
        ]
        if missing:
            return _missing_result("calcular_vk", missing)

        vk = calcular_vk(params["v0"], params["s1"], params["s2"], params["s3"])
        markdown = f"""A velocidade característica do vento é calculada por:

**Fórmula:**
$$V_k = V_0 S_1 S_2 S_3$$

**Valores:**
- $V_0 = {_fmt(params['v0'])}\\,m/s$
- $S_1 = {_fmt(params['s1'], 3)}$
- $S_2 = {_fmt(params['s2'], 3)}$
- $S_3 = {_fmt(params['s3'], 3)}$

**Substituição:**
$$V_k = {_fmt(params['v0'])} \\cdot {_fmt(params['s1'], 3)} \\cdot {_fmt(params['s2'], 3)} \\cdot {_fmt(params['s3'], 3)}$$

**Resultado:**
$$V_k = {_fmt(vk)}\\,m/s$$

Fonte: NBR 6123, fórmula da velocidade característica do vento."""
        return CalculationResult(
            handled=True,
            operation="calcular_vk",
            markdown=markdown,
            values={**params, "vk": vk},
            sources=[_source("3.1", "4")],
        )

    def _handle_q(self, params: dict) -> CalculationResult:
        working = dict(params)
        if "vk" not in working and all(key in working for key in ["v0", "s1", "s2", "s3"]):
            working["vk"] = calcular_vk(working["v0"], working["s1"], working["s2"], working["s3"])

        if "vk" not in working:
            return _missing_result(
                "calcular_q",
                ["$V_k$ ou, alternativamente, $V_0$, $S_1$, $S_2$ e $S_3$"],
            )

        q = calcular_q(working["vk"])
        vk_block = ""
        if all(key in working for key in ["v0", "s1", "s2", "s3"]):
            vk_block = f"""Primeiro:
$$V_k = V_0 S_1 S_2 S_3 = {_fmt(working['v0'])} \\cdot {_fmt(working['s1'], 3)} \\cdot {_fmt(working['s2'], 3)} \\cdot {_fmt(working['s3'], 3)} = {_fmt(working['vk'])}\\,m/s$$

"""
        markdown = f"""{vk_block}A pressão dinâmica é calculada por:

**Fórmula:**
$$q = 0,613 V_k^2$$

**Valores:**
- $V_k = {_fmt(working['vk'])}\\,m/s$

**Substituição:**
$$q = 0,613 \\cdot {_fmt(working['vk'])}^2$$

**Resultado:**
$$q = {_fmt(q)}\\,N/m^2$$

Fonte: NBR 6123, seção 4.2."""
        return CalculationResult(
            handled=True,
            operation="calcular_q",
            markdown=markdown,
            values={**working, "q": q},
            sources=[_source("4.2", "8")],
        )

    def _handle_force(self, params: dict) -> CalculationResult:
        missing = [
            label for key, label in [("q", "$q$"), ("c", "$C$"), ("a", "$A$")]
            if key not in params
        ]
        if missing:
            return _missing_result("calcular_forca", missing)

        force = calcular_forca(params["q"], params["c"], params["a"])
        markdown = f"""A força do vento pode ser calculada pela expressão geral:

**Fórmula:**
$$F = q C A$$

**Valores:**
- $q = {_fmt(params['q'])}\\,N/m^2$
- $C = {_fmt(params['c'], 3)}$
- $A = {_fmt(params['a'])}\\,m^2$

**Substituição:**
$$F = {_fmt(params['q'])} \\cdot {_fmt(params['c'], 3)} \\cdot {_fmt(params['a'])}$$

**Resultado:**
$$F = {_fmt(force)}\\,N$$

Fonte: NBR 6123, expressão geral de força do vento."""
        return CalculationResult(
            handled=True,
            operation="calcular_forca",
            markdown=markdown,
            values={**params, "f": force},
            sources=[_source("4.1", "7")],
        )

    def _handle_delta_p(self, params: dict) -> CalculationResult:
        missing = [
            label for key, label in [("cpe", "$c_{pe}$"), ("cpi", "$c_{pi}$"), ("q", "$q$")]
            if key not in params
        ]
        if missing:
            return _missing_result("calcular_delta_p", missing)

        delta_p = calcular_delta_p(params["cpe"], params["cpi"], params["q"])
        markdown = f"""A pressão efetiva é calculada por:

**Fórmula:**
$$\\Delta p = (c_{{pe}} - c_{{pi}})q$$

**Substituição:**
$$\\Delta p = ({_fmt(params['cpe'], 3)} - {_fmt(params['cpi'], 3)}) \\cdot {_fmt(params['q'])}$$

**Resultado:**
$$\\Delta p = {_fmt(delta_p)}\\,N/m^2$$"""
        return CalculationResult(
            handled=True,
            operation="calcular_delta_p",
            markdown=markdown,
            values={**params, "delta_p": delta_p},
            sources=[_source("4.3.1", "9")],
        )

    def _handle_pe(self, params: dict) -> CalculationResult:
        missing = [label for key, label in [("cpe", "$c_{pe}$"), ("q", "$q$")] if key not in params]
        if missing:
            return _missing_result("calcular_pressao_externa", missing)
        pe = calcular_pressao_externa(params["cpe"], params["q"])
        markdown = f"""**Fórmula:**
$$\\Delta p_e = c_{{pe}}q$$

**Substituição:**
$$\\Delta p_e = {_fmt(params['cpe'], 3)} \\cdot {_fmt(params['q'])}$$

**Resultado:**
$$\\Delta p_e = {_fmt(pe)}\\,N/m^2$$"""
        return CalculationResult(True, "calcular_pressao_externa", markdown, values={**params, "pe": pe}, sources=[_source("6.3.3", "45")])

    def _handle_pi(self, params: dict) -> CalculationResult:
        missing = [label for key, label in [("cpi", "$c_{pi}$"), ("q", "$q$")] if key not in params]
        if missing:
            return _missing_result("calcular_pressao_interna", missing)
        pi = calcular_pressao_interna(params["cpi"], params["q"])
        markdown = f"""**Fórmula:**
$$\\Delta p_i = c_{{pi}}q$$

**Substituição:**
$$\\Delta p_i = {_fmt(params['cpi'], 3)} \\cdot {_fmt(params['q'])}$$

**Resultado:**
$$\\Delta p_i = {_fmt(pi)}\\,N/m^2$$"""
        return CalculationResult(True, "calcular_pressao_interna", markdown, values={**params, "pi": pi}, sources=[_source("6.3.3", "45")])

    def _handle_s2(self, params: dict) -> CalculationResult:
        missing = [
            label for key, label in [
                ("categoria", "categoria de rugosidade"),
                ("classe", "classe A, B ou C"),
                ("z", "altura $z$ em metros"),
            ]
            if key not in params
        ]
        if missing:
            return _missing_result("calcular_s2", missing)

        data = calcular_s2(params["categoria"], params["classe"], params["z"])
        markdown = f"""O fator $S_2$ é calculado por:

**Fórmula:**
$$S_2 = b_m F_r \\left(\\frac{{z}}{{10}}\\right)^p$$

**Valores:**
- Categoria: {data['categoria']}
- Classe: {data['classe']}
- $z = {_fmt(float(data['z']))}\\,m$
- $b_m = {_fmt(float(data['bm']), 3)}$
- $F_r = {_fmt(float(data['fr']), 3)}$
- $p = {_fmt(float(data['p']), 3)}$

**Substituição:**
$$S_2 = {_fmt(float(data['bm']), 3)} \\cdot {_fmt(float(data['fr']), 3)} \\cdot \\left(\\frac{{{_fmt(float(data['z']))}}}{{10}}\\right)^{{{_fmt(float(data['p']), 3)}}}$$

**Resultado:**
$$S_2 = {_fmt(float(data['s2']), 3)}$$

Fonte: NBR 6123, seção 5.3.3 e Tabela 3."""
        return CalculationResult(
            handled=True,
            operation="calcular_s2",
            markdown=markdown,
            values=data,
            sources=[_source("5.3.3", "14"), _source("5.4", "16", "tabela")],
        )

    def _handle_s3(self, params: dict) -> CalculationResult:
        if "grupo" not in params:
            return _missing_result("buscar_s3", ["grupo da edificação"])
        data = buscar_s3(params["grupo"])
        markdown = f"""Para o grupo {data['grupo']}, o fator estatístico é:

**Valor:**
$$S_3 = {_fmt(float(data['s3']), 3)}$$

Tempo de recorrência associado na tabela: {data['tp']} anos.

Fonte: NBR 6123, Tabela 4."""
        return CalculationResult(True, "buscar_s3", markdown, values=data, sources=[_source("5.5", "17", "tabela")])
