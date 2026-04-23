import os
import json
import argparse
import time
import fitz
import re
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

# =========================================================
# CONFIG
# =========================================================
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY não encontrada no .env")

client = genai.Client(api_key=GOOGLE_API_KEY)

BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_NAME = "gemini-2.0-flash"

SAVE_RAW_DEBUG = True

PROMPT_ESTRUTURADO = r"""
Você é um engenheiro especialista em normas técnicas.

Sua tarefa é estruturar o conteúdo desta página de uma norma técnica em JSON válido.

Você receberá:
1. A IMAGEM da página
2. O TEXTO BRUTO extraído diretamente do PDF
3. FÓRMULAS CANDIDATAS detectadas automaticamente no texto
4. Um CONTEXTO CURTO da página anterior

PRINCÍPIOS:
- Use o TEXTO BRUTO como base principal.
- Use a IMAGEM para confirmar headings, fórmulas, tabelas e legenda de figura.
- Use as FÓRMULAS CANDIDATAS como apoio: aproveite as corretas e descarte as erradas.
- NÃO invente conteúdo.
- NÃO copiar conteúdo da página anterior para a atual.
- NÃO omitir fórmulas que estejam claramente presentes na página.

=========================================================
RETORNE APENAS ESTES CAMPOS
=========================================================
- numero_pagina_impresso
- tipo_pagina
- secao_iniciada_na_pagina
- ultima_secao_detectada
- secao_continua_na_proxima
- texto_teorico
- tabelas
- formulas
- figura_legenda
- curvas_ou_rotulos

=========================================================
REGRAS DE ESTRUTURA NORMATIVA
=========================================================
- Detecte a seção iniciada na página, se houver.
- Detecte a última seção ativa da página.
- Indique se a seção continua na próxima página apenas se isso estiver claro.
- Só crie cabeçalhos Markdown quando eles estiverem realmente visíveis na página.
- O nível do heading depende da profundidade da seção:
  - 5 -> #
  - 5.1 -> ##
  - 5.5.1 -> ###
  - 6.1.2.1 -> ####

=========================================================
REGRAS PARA texto_teorico
=========================================================
- O campo "texto_teorico" deve conter:
  - títulos de seções/subseções
  - texto explicativo corrido
  - listas/alíneas normativas
  - itens de nomenclatura, símbolos e definições, quando fizerem parte do corpo da página
- NÃO coloque no texto:
  - linhas de tabela estruturadas
  - conteúdo tabular duplicado
  - repetição desnecessária de fórmulas destacadas
- Preserve variáveis normativas em LaTeX inline:
  - $V_0$, $S_1$, $S_2$, $S_3$, $V_k$, $q$, $z_x$, $z_i$, $z_0$, $z_g$, $z_{01}$, $z_{02}$

=========================================================
REGRAS PARA formulas
=========================================================
- Extraia TODAS as fórmulas/equações explicitamente presentes na página.
- Considere também as fórmulas candidatas recebidas.
- NÃO crie fórmula só porque um símbolo aparece numa definição curta, a menos que a expressão esteja claramente presente.
- Cada fórmula deve conter:
  - "secao"
  - "titulo_secao"
  - "descricao"
  - "equacao"
- A equação deve vir em LaTeX com delimitadores $$...$$
- Preserve a grafia matemática fiel à página.
- Não use texto narrativo dentro da equação.
- Se houver logaritmo natural, use \ln quando estiver claro.
- Não use \text{In}.
- Se a seção da fórmula estiver clara, preencha.
- Caso contrário, use a seção ativa da página apenas se fizer sentido documental.

=========================================================
REGRAS PARA tabelas
=========================================================
- Se houver tabela explícita, extraia em "tabelas".
- Cada tabela deve conter:
  - "titulo"
  - "dados"
- Preserve a estrutura da tabela da forma mais fiel possível.
- Não resuma.
- Não transforme gráfico em tabela.
- Se a tabela for complexa, mantenha a estrutura mais rica que conseguir, em vez de retornar "dados": {}.
- Nunca retornar "dados": {} se houver conteúdo legível na tabela.

=========================================================
REGRAS PARA figura_legenda
=========================================================
- Se houver figura, gráfico, curva, mapa ou diagrama com legenda/título visível, preencha "figura_legenda".
- Se não houver, use null.
- Não invente valores não legíveis.

=========================================================
FORMATO OBRIGATÓRIO
=========================================================
{
  "numero_pagina_impresso": "número impresso da página ou null",
  "secao_iniciada_na_pagina": "ex: 5.5.1 ou null",
  "ultima_secao_detectada": "ex: 5.5.1 ou null",
  "secao_continua_na_proxima": true,
  "texto_teorico": "markdown ou null",
  "tabelas": [
    {
      "titulo": "Tabela 4 - Valores mínimos do fator estatístico $S_3$",
      "dados": {
        "headers": [],
        "rows": []
      }
    }
  ],
  "formulas": [
    {
      "secao": "5.5.1",
      "titulo_secao": "Transição para categoria de rugosidade maior",
      "descricao": "Equação para determinar $z_x$",
      "equacao": "$$z_x = A z_{02} (x / z_{02})^{0,8}$$"
    }
  ],
  "figura_legenda": "Figura 1 – Isopletas de velocidade básica $V_0$ (m/s)"
}

IMPORTANTE:
- Retorne APENAS JSON válido.
- Se algum campo não existir, use:
  - texto_teorico: null
  - tabelas: []
  - formulas: []
  - figura_legenda: null
"""

PROMPT_TABELA_ESPECIALIZADO = r"""
Você é um engenheiro especialista em normas técnicas.

Sua única tarefa é extrair a tabela presente nesta página.

REGRAS:
- Não resuma a tabela.
- Não retornar "dados": {} se houver conteúdo legível.
- Preserve todos os cabeçalhos.
- Preserve subcabeçalhos e hierarquia quando existirem.
- Preserve linhas e colunas.
- Se a tabela for complexa, retorne a estrutura mais rica possível.
- Se não conseguir inferir uma estrutura hierárquica perfeita, retorne ao menos:
  - headers
  - rows
- Não misture texto corrido fora da tabela.
- Não extrair fórmulas fora da tabela.
- Não explicar a tabela; apenas estruturá-la.
- Se houver mais de uma tabela na página, retorne todas.
- Se a tabela tiver título visível, preserve.
- Se a tabela tiver conteúdo legível, NÃO deixe "dados": {}.

FORMATO OBRIGATÓRIO:
{
  "tabelas": [
    {
      "titulo": "Título da tabela ou null",
      "dados": {
        "headers": [],
        "rows": []
      }
    }
  ]
}

IMPORTANTE:
- Retorne APENAS JSON válido.
- Só use "tabelas": [] se a página realmente não tiver tabela explícita.
"""

JSON_CLEANUP_RE = re.compile(r'(?<!\\)\\(?![\\"/bfnrtu])')

SECTION_LINE_RE = re.compile(
    r"^\s*(#{0,6})\s*((?:\d+)(?:\.\d+){0,10})\s+(.*\S)?\s*$"
)

HEADER_CAPTURE_RE = re.compile(
    r"^\s*#{1,6}\s+((?:\d+)(?:\.\d+){0,10})\s+(.*\S)\s*$",
    re.MULTILINE
)

TABLE_TITLE_RE = re.compile(r"^\s*(ABNT\s+NBR.*|Tabela\s+\d+.*)$", re.IGNORECASE)
MARKDOWN_TABLE_RE = re.compile(r"^\s*\|.*\|\s*$")

FORMULA_LHS_RE = re.compile(
    r"""
    ^\s*
    (?P<lhs>
        [A-Za-zΔρψφθζηγςαβωΩΛΠΣVSCFqazmtxkT]
        [A-Za-z0-9_{}\(\)\\]*
    )
    \s*=
    """,
    re.VERBOSE
)

FORMULA_EXPR_RE = re.compile(
    r"""
    (?P<expr>
        [A-Za-zΔρψφθζηγςαβωΩΛΠΣVSCFqazmtxkT]
        [A-Za-z0-9_{}\-\+\(\)\[\]\s\\/,\.°≤≥<>^]*=
        [A-Za-z0-9_{}\-\+\(\)\[\]\s\\/,\.°≤≥<>^]+
    )
    """,
    re.VERBOSE
)

MATH_SIGNAL_RE = re.compile(r"(=|/|\+|-|\^|\\frac|\\ln|\\tg|≤|≥|<|>)")


# =========================================================
# VALIDACAO SEMANTICA DA EXTRACAO
# =========================================================
VALID_PAGE_TYPES = {"texto_normativo", "nomenclatura", "figura_grafico", "tabela", "mista"}
VALID_FORMULA_TYPES = {"calculo", "definicao", "grafico_rotulo"}
VALID_FORMULA_ORIGINS = {
    "equacao_destacada",
    "inline_definicao",
    "texto_pdf",
    "imagem",
    "rotulo_grafico",
}

GRAPH_LABEL_LHS_RE = re.compile(
    r"^(?:\\?zeta|ζ|ξ|\\?xi|\\?theta|θ|\\?psi|ψ)$",
    re.IGNORECASE,
)

NORMATIVE_SIMPLE_ASSIGNMENT_LHS = {
    "s1",
    "s2",
    "s3",
    "v0",
    "vk",
    "vp",
    "q",
    "alim",
    "kc",
}


# =========================================================
# HELPERS GERAIS
# =========================================================
def limpar_json_quebrado(texto_bruto: str) -> str:
    return JSON_CLEANUP_RE.sub(r"\\\\", texto_bruto)


def salvar_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def resumir_contexto_anterior(raw_anterior: dict | None) -> str:
    if not raw_anterior:
        return "Sem contexto anterior."

    pagina = raw_anterior.get("numero_pagina_impresso")
    secao_inicial = raw_anterior.get("secao_iniciada_na_pagina")
    ultima_secao = raw_anterior.get("ultima_secao_detectada")
    continua = raw_anterior.get("secao_continua_na_proxima")
    texto = raw_anterior.get("texto_teorico") or ""

    texto_limpo = " ".join(texto.split())
    trecho_final = texto_limpo[-1200:] if len(texto_limpo) > 1200 else texto_limpo

    return (
        f"Página anterior impressa: {pagina}\n"
        f"Seção iniciada na página anterior: {secao_inicial}\n"
        f"Última seção detectada: {ultima_secao}\n"
        f"Continua na próxima: {continua}\n"
        f"Trecho final da página anterior:\n{trecho_final}"
    )


def normalizar_pagina_real(pagina_real, fallback_pdf_num: int) -> str:
    if pagina_real is None:
        return f"sem_numero_{fallback_pdf_num}"
    pagina_real_str = str(pagina_real).strip()
    if not pagina_real_str:
        return f"sem_numero_{fallback_pdf_num}"
    return pagina_real_str


def get_heading_level_from_section(section_number: str) -> int:
    parts = [p for p in section_number.split(".") if p.strip()]
    return max(1, min(len(parts), 6))


def normalize_inline_latex_in_titles(text: str) -> str:
    """
    Normaliza variáveis em títulos, legendas e descrições curtas.
    """
    if not text:
        return text

    replacements = [
        (r"\bS1\b", r"$S_1$"),
        (r"\bS2\b", r"$S_2$"),
        (r"\bS3\b", r"$S_3$"),
        (r"\bV0\b", r"$V_0$"),
        (r"\bVk\b", r"$V_k$"),
        (r"\bVp\b", r"$V_p$"),
        (r"\bTp\b", r"$T_p$"),
        (r"\bzx\b", r"$z_x$"),
        (r"\bzi\b", r"$z_i$"),
        (r"\bz0\b", r"$z_0$"),
        (r"\bzg\b", r"$z_g$"),
        (r"\bz01\b", r"$z_{01}$"),
        (r"\bz02\b", r"$z_{02}$"),
        (r"\bCa\b", r"$C_a$"),
        (r"\bCe\b", r"$C_e$"),
        (r"\bCf\b", r"$C_f$"),
        (r"\bCi\b", r"$C_i$"),
        (r"\bCt\b", r"$C_t$"),
        (r"\bCx\b", r"$C_x$"),
        (r"\bCy\b", r"$C_y$"),
        (r"\bcp\b", r"$c_p$"),
        (r"\bcpe\b", r"$c_{pe}$"),
        (r"\bcpi\b", r"$c_{pi}$"),
        (r"\bVo\b", r"$V_0$"),
    ]

    out = text
    for pattern, repl in replacements:
        out = re.sub(pattern, repl, out)

    return out


def normalize_markdown_headings(text: str) -> str:
    if not text:
        return text

    normalized_lines = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        match = SECTION_LINE_RE.match(line)

        if match:
            _existing_hashes, section_number, title = match.groups()
            level = get_heading_level_from_section(section_number)
            hashes = "#" * level
            title = normalize_inline_latex_in_titles((title or "").strip())

            if title:
                normalized_lines.append(f"{hashes} {section_number} {title}")
            else:
                normalized_lines.append(f"{hashes} {section_number}")
        else:
            normalized_lines.append(line)

    return "\n".join(normalized_lines).strip()


def clean_textual_leakage(text: str) -> str:
    if not text:
        return text

    cleaned = []
    inside_markdown_table = False

    for line in text.splitlines():
        stripped = line.strip()

        if TABLE_TITLE_RE.match(stripped):
            continue

        if MARKDOWN_TABLE_RE.match(stripped):
            inside_markdown_table = True
            continue

        if inside_markdown_table and re.match(r"^\s*\|?\s*:?-{2,}", stripped):
            continue

        if inside_markdown_table and not stripped:
            inside_markdown_table = False
            continue

        if inside_markdown_table:
            continue

        cleaned.append(line)

    return "\n".join(cleaned).strip()


def normalize_for_text_match(text: str) -> str:
    text = text or ""
    text = text.lower()
    text = text.replace("\\delta", "delta")
    text = text.replace("∆", "delta").replace("Δ", "delta")
    text = text.replace("δ", "delta")
    text = re.sub(r"delta\s*\$?\s*p", "deltap", text)
    text = re.sub(r"delta\s*p", "deltap", text)
    text = text.replace("c_{pe}", "cpe").replace("c_{pi}", "cpi")
    text = text.replace("c_pe", "cpe").replace("c_pi", "cpi")
    text = text.replace("p_e", "pe").replace("p_i", "pi")
    text = re.sub(r"[$#*_`|]", "", text)
    text = text.replace("{", "").replace("}", "")
    text = text.replace("\\", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def token_set_for_overlap(text: str) -> set[str]:
    normalized = normalize_for_text_match(text)
    return {
        token
        for token in re.findall(r"[a-z0-9]+", normalized)
        if len(token) > 2
    }


def is_pdf_noise_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if re.fullmatch(r"\d{1,4}", stripped):
        return True
    if re.match(r"^ABNT\s+NBR", stripped, re.IGNORECASE):
        return True
    if "©" in stripped or "todos os direitos" in stripped.lower():
        return True
    return False


def clean_raw_prefix_text(prefix: str) -> str:
    lines = []
    for line in (prefix or "").splitlines():
        stripped = line.strip()
        if is_pdf_noise_line(stripped):
            continue
        lines.append(stripped)

    text = "\n".join(lines).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def recover_raw_top_continuation(texto_teorico: str | None, raw_text: str) -> str | None:
    if not texto_teorico or not raw_text:
        return texto_teorico

    first_heading = HEADER_CAPTURE_RE.search(texto_teorico)
    if not first_heading:
        return texto_teorico

    section = first_heading.group(1).strip()
    heading_pattern = re.compile(
        rf"^\s*{re.escape(section)}\s+.*$",
        re.MULTILINE,
    )
    raw_heading = heading_pattern.search(raw_text)
    if not raw_heading or raw_heading.start() <= 0:
        return texto_teorico

    raw_prefix = clean_raw_prefix_text(raw_text[:raw_heading.start()])
    if len(raw_prefix) < 80:
        return texto_teorico

    text_norm = normalize_for_text_match(texto_teorico)
    prefix_norm = normalize_for_text_match(raw_prefix)

    if not prefix_norm:
        return texto_teorico

    # If the prefix is already mostly present, do not duplicate it.
    prefix_probe = prefix_norm[: min(len(prefix_norm), 220)]
    if prefix_probe and prefix_probe in text_norm:
        return texto_teorico

    prefix_tokens = token_set_for_overlap(raw_prefix)
    text_start = texto_teorico[: max(600, len(raw_prefix) * 2)]
    text_tokens = token_set_for_overlap(text_start)
    if prefix_tokens:
        overlap = len(prefix_tokens & text_tokens) / len(prefix_tokens)
        if overlap >= 0.62:
            return texto_teorico

    return f"{raw_prefix}\n\n{texto_teorico}".strip()


def remove_structured_table_from_text(text: str, tabelas: list[dict]) -> str:
    if not text or not tabelas:
        return text

    lines = text.splitlines()
    cleaned = []
    idx = 0
    removed_any = False

    table_headers = []
    for tabela in tabelas:
        dados = tabela.get("dados") or {}
        headers = dados.get("headers") or []
        if headers:
            table_headers.extend(str(h).strip() for h in headers if str(h).strip())

    header_tokens = {h for h in table_headers if len(h) <= 20}
    table_start_tokens = {"Grupo", "Descrição", "$S_3$", "S3", "$T_p$", "Tp", "z", "z (m)", "Parâmetro"}

    while idx < len(lines):
        stripped = lines[idx].strip()
        starts_like_table = stripped in table_start_tokens or stripped in header_tokens

        if starts_like_table:
            lookahead = [ln.strip() for ln in lines[idx:idx + 40] if ln.strip()]
            numeric_count = sum(1 for ln in lookahead if re.fullmatch(r"\d+(?:,\d+)?|[IVX]+|[ABC]|≤?\d+", ln))
            header_count = sum(1 for ln in lookahead if ln in header_tokens or ln in table_start_tokens)

            if header_count >= 2 and numeric_count >= 3:
                while idx < len(lines):
                    current = lines[idx].strip()
                    if current.startswith("#"):
                        break
                    if re.match(r"^\d+(?:\.\d+)+\s+", current):
                        break
                    idx += 1
                cleaned.append("[Tabela extraída em arquivo JSON nesta página]")
                removed_any = True
                continue

        cleaned.append(lines[idx])
        idx += 1

    out = "\n".join(cleaned).strip()
    if removed_any:
        out = re.sub(r"\n{3,}", "\n\n", out)
    return out


def normalize_inline_variables(text: str) -> str:
    if not text:
        return text

    replacements = [
        (r"\bS1\b", r"$S_1$"),
        (r"\bS2\b", r"$S_2$"),
        (r"\bS3\b", r"$S_3$"),
        (r"\bV0\b", r"$V_0$"),
        (r"\bVk\b", r"$V_k$"),
        (r"\bTp\b", r"$T_p$"),
        (r"\bzx\b", r"$z_x$"),
        (r"\bzi\b", r"$z_i$"),
        (r"\bz0\b", r"$z_0$"),
        (r"\bzg\b", r"$z_g$"),
        (r"\bz01\b", r"$z_{01}$"),
        (r"\bz02\b", r"$z_{02}$"),
    ]

    out = text
    for pattern, repl in replacements:
        out = re.sub(pattern, repl, out)

    return out


def extract_last_section_from_text(text: str) -> tuple[str | None, str | None]:
    if not text:
        return None, None

    matches = list(HEADER_CAPTURE_RE.finditer(text))
    if not matches:
        return None, None

    last = matches[-1]
    return last.group(1).strip(), normalize_inline_latex_in_titles(last.group(2).strip())


def ensure_formula_minimum_fields(
    formula: dict,
    pagina_real: str,
    idx: int,
    secao_fallback: str | None,
    titulo_fallback: str | None
) -> dict:
    formula["pagina"] = pagina_real
    formula["formula_index_na_pagina"] = idx
    formula["formula_id"] = f"pag_{pagina_real}_formula_{idx}"

    if not formula.get("secao"):
        formula["secao"] = secao_fallback
    if not formula.get("titulo_secao"):
        formula["titulo_secao"] = titulo_fallback

    if formula.get("titulo_secao"):
        formula["titulo_secao"] = normalize_inline_latex_in_titles(formula["titulo_secao"])

    descricao = (formula.get("descricao") or "").strip()
    if not descricao:
        formula["descricao"] = "Equação extraída da norma"
    else:
        formula["descricao"] = normalize_inline_latex_in_titles(descricao)

    equacao = (formula.get("equacao") or "").strip()
    if equacao and not equacao.startswith("$$"):
        equacao = "$$" + equacao
    if equacao and not equacao.endswith("$$"):
        equacao = equacao + "$$"
    formula["equacao"] = equacao

    return formula

SIMPLE_ASSIGNMENT_RE = re.compile(
    r"""
    ^\$\$
    \s*
    (?P<lhs>[A-Za-z\\][A-Za-z0-9_{}\(\)\\]*)
    \s*=\s*
    (?P<rhs>[0-9]+([.,][0-9]+)?)
    \s*
    \$\$
    """,
    re.VERBOSE
)

def is_simple_numeric_assignment(equacao: str) -> bool:
    """
    Detecta fórmulas do tipo:
    $$S_1 = 1,0$$
    $$S_1 = 0,9$$
    """
    if not equacao:
        return False
    return SIMPLE_ASSIGNMENT_RE.match(equacao.strip()) is not None


def is_normative_simple_assignment(equacao: str, descricao: str | None = None) -> bool:
    if not is_simple_numeric_assignment(equacao):
        return False

    lhs = extract_formula_lhs(equacao)
    descricao_lower = (descricao or "").lower()

    if lhs in NORMATIVE_SIMPLE_ASSIGNMENT_LHS:
        return True

    normative_words = [
        "terreno",
        "topogr",
        "vale",
        "talude",
        "morro",
        "ponto",
        "categoria",
        "fator",
    ]
    return any(word in descricao_lower for word in normative_words)


def prune_redundant_formulas(formulas: list[dict]) -> list[dict]:
    """
    Remove fórmulas simples demais quando houver fórmulas mais ricas na mesma página.
    Mantém:
    - fórmulas com operadores/variáveis no lado direito
    - fórmulas realmente explicativas
    Remove:
    - atribuições numéricas simples repetitivas
    """
    if not formulas:
        return formulas

    rich_formulas = []
    simple_formulas = []

    for f in formulas:
        eq = (f.get("equacao") or "").strip()

        if is_simple_numeric_assignment(eq) and not is_normative_simple_assignment(eq, f.get("descricao")):
            simple_formulas.append(f)
        else:
            rich_formulas.append(f)

    # se não houver fórmula rica, mantém tudo
    if not rich_formulas:
        return formulas

    # se houver fórmula rica, descartamos as atribuições simples
    return rich_formulas[:]

def reindex_formulas(formulas: list[dict], pagina_real: str) -> list[dict]:
    """
    Reindexa formula_index_na_pagina e formula_id após filtros.
    """
    out = []
    for idx, formula in enumerate(formulas, start=1):
        formula["formula_index_na_pagina"] = idx
        formula["formula_id"] = f"pag_{pagina_real}_formula_{idx}"
        out.append(formula)
    return out


# =========================================================
# PYMUPDF / TEXTO BRUTO
# =========================================================
def extract_pdf_text(page: fitz.Page) -> str:
    return page.get_text("text").strip()


# =========================================================
# DETECÇÃO DE FÓRMULAS CANDIDATAS
# =========================================================
def build_formula_description(prefix: str, expr: str) -> str:
    prefix = (prefix or "").strip(" :;,-")
    expr = (expr or "").strip()

    if prefix:
        return prefix

    lhs = expr.split("=", 1)[0].strip()
    if lhs:
        return f"Equação para determinar {lhs}"

    return "Fórmula detectada no texto da página"


def normalize_lhs_token(lhs: str) -> str:
    lhs = lhs.strip()
    lhs = lhs.replace("{", "").replace("}", "")
    lhs = lhs.replace("\\", "")
    lhs = lhs.replace("_", "")
    lhs = lhs.replace(" ", "")
    return lhs


def is_valid_formula_candidate(prefix: str, expr: str) -> bool:
    if not expr or "=" not in expr:
        return False

    expr = expr.strip()
    prefix = (prefix or "").strip()

    if len(expr) > 120:
        return False

    lhs = expr.split("=", 1)[0].strip()
    if not FORMULA_LHS_RE.match(f"{lhs}="):
        return False

    lhs_norm = normalize_lhs_token(lhs)
    if len(lhs_norm) > 12:
        return False

    rhs = expr.split("=", 1)[1].strip()
    if len(rhs) < 1:
        return False

    if not MATH_SIGNAL_RE.search(expr):
        return False

    banned_words = [
        "onde",
        "sendo",
        "valor de",
        "corresponde",
        "considera",
        "definido em",
        "expresso em",
    ]
    expr_lower = expr.lower()
    if any(word in expr_lower for word in banned_words):
        return False

    return True


def extract_formula_candidates(raw_text: str) -> list[dict]:
    if not raw_text:
        return []

    candidates = []
    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]

    for line in lines:
        if "=" not in line:
            continue

        if len(line) > 220:
            continue

        match = FORMULA_EXPR_RE.search(line)
        if not match:
            continue

        expr = match.group("expr").strip()
        prefix = line[:match.start()].strip()

        prefix = prefix.rstrip(":;,. ")
        expr = expr.strip(" :;,")

        if not is_valid_formula_candidate(prefix, expr):
            continue

        candidates.append({
            "descricao": build_formula_description(prefix, expr),
            "equacao": expr,
        })

    seen = set()
    out = []
    for item in candidates:
        key = re.sub(r"\s+", "", item["equacao"])
        if key not in seen:
            seen.add(key)
            out.append(item)

    return out


def normalize_formula_string(s: str) -> str:
    if not s:
        return ""

    s = s.strip()
    s = s.removeprefix("$$").removesuffix("$$").strip()
    s = s.lower()
    s = s.replace("ψ", "psi").replace("ζ", "zeta").replace("ξ", "xi").replace("θ", "theta")
    s = s.replace("∆", "delta").replace("Δ", "delta")
    s = s.replace("{", "").replace("}", "")
    s = s.replace("\\", "")
    s = s.replace("_", "")
    s = re.sub(r"\s+", "", s)
    s = s.replace("−", "-").replace("–", "-")
    s = s.replace(",", ".")

    return s


def normalize_formula_equivalence(s: str) -> str:
    out = normalize_formula_string(s)
    out = out.replace("deltape", "deltap_e").replace("deltapi", "deltap_i")
    out = out.replace("cpe", "c_pe").replace("cpi", "c_pi")
    out = out.replace("ce", "c_e").replace("ci", "c_i")
    out = re.sub(r"frac([^/=\+\-\*]+)([^/=\+\-\*]+)", r"\1/\2", out)
    out = out.replace("deltap_e/q", "deltape/q")
    out = out.replace("deltap_i/q", "deltapi/q")
    out = out.replace("c_pe", "cpe").replace("c_pi", "cpi")
    out = out.replace("c_e", "ce").replace("c_i", "ci")
    out = out.replace("operatornametg", "tg").replace("tan", "tg")
    out = out.replace("\\text", "text")
    return out


def extract_formula_lhs(expr: str) -> str:
    if not expr or "=" not in expr:
        return ""

    lhs = expr.split("=", 1)[0].strip()
    return normalize_formula_string(lhs)


def infer_page_type(dados: dict, texto_teorico: str | None, raw_text: str) -> str:
    tipo = (dados.get("tipo_pagina") or "").strip()
    has_text = bool((texto_teorico or "").strip())
    has_tables = bool(dados.get("tabelas"))
    has_figure = bool(dados.get("figura_legenda"))

    raw_len = len((raw_text or "").strip())

    if has_tables and has_text:
        return "mista"
    if tipo in VALID_PAGE_TYPES and tipo != "tabela":
        return tipo
    if has_tables and not has_text:
        return "tabela"
    if has_figure and (not has_text or raw_len < 500):
        return "figura_grafico"
    if has_figure and has_text:
        return "mista"
    if raw_len < 220 and not has_text and has_figure:
        return "figura_grafico"
    return "texto_normativo"


def classify_formula_type(formula: dict) -> str:
    tipo = (formula.get("tipo_formula") or "").strip()
    if tipo in VALID_FORMULA_TYPES:
        return tipo

    origem = (formula.get("origem") or "").strip()
    descricao = (formula.get("descricao") or "").lower()
    equacao = formula.get("equacao") or ""

    if origem == "rotulo_grafico":
        return "grafico_rotulo"
    equacao_norm = normalize_formula_string(equacao)
    lhs_norm = extract_formula_lhs(equacao)
    if lhs_norm in {"cpe", "cpi", "ce", "ci", "ca", "cf", "ct", "cx", "cy"}:
        return "definicao"
    if any(token in equacao_norm for token in ["cpe=", "cpi=", "ce=", "ci=", "ca=", "cf=", "ct="]):
        return "definicao"
    if any(token in descricao for token in ["coeficiente", "definid", "grandeza", "simbolo", "símbolo"]):
        return "definicao"
    if ";" in descricao and "=" in equacao:
        return "definicao"
    return "calculo"


def classify_formula_origin(formula: dict) -> str:
    origem = (formula.get("origem") or "").strip()
    if origem in VALID_FORMULA_ORIGINS:
        return origem

    descricao = (formula.get("descricao") or "").lower()
    if any(token in descricao for token in ["coeficiente", "definid", "grandeza", "simbolo", "símbolo"]):
        return "inline_definicao"
    return "texto_pdf"


def is_graph_label_formula(formula: dict, tipo_pagina: str) -> bool:
    equacao = (formula.get("equacao") or "").strip()
    if "=" not in equacao:
        return False

    raw = equacao.removeprefix("$$").removesuffix("$$").strip()
    lhs = normalize_formula_string(raw.split("=", 1)[0])
    rhs = normalize_formula_string(raw.split("=", 1)[1])

    if formula.get("tipo_formula") == "grafico_rotulo" or formula.get("origem") == "rotulo_grafico":
        return True

    if tipo_pagina != "figura_grafico":
        return False

    if GRAPH_LABEL_LHS_RE.match(lhs) and re.fullmatch(r"[0-9.,%]+", rhs):
        return True

    if GRAPH_LABEL_LHS_RE.match(lhs) and len(rhs) <= 6:
        return True

    return False


def is_bad_delta_p_loss(formula: dict, existing_formulas: list[dict] | None = None) -> bool:
    equacao = formula.get("equacao") or ""
    body = strip_math_delimiters(equacao)
    lhs = normalize_formula_string(body.split("=", 1)[0]) if "=" in body else ""
    rhs = normalize_formula_equivalence(body.split("=", 1)[1]) if "=" in body else ""

    if lhs != "p":
        return False

    if not any(token in rhs for token in ["deltape", "deltapi", "cpe", "cpi"]):
        return False

    for existing in existing_formulas or []:
        existing_lhs = extract_formula_lhs(existing.get("equacao") or "")
        existing_key = normalize_formula_equivalence(existing.get("equacao") or "")
        if existing_lhs in {"deltap", "deltap_e", "deltap_i"} or "deltap" in existing_key:
            return True

    return True


def normalize_formula_metadata(formula: dict) -> dict:
    formula["equacao"] = clean_formula_equation(formula.get("equacao") or "")
    formula["tipo_formula"] = classify_formula_type(formula)
    formula["origem"] = classify_formula_origin(formula)

    status = (formula.get("status_validacao") or "").strip()
    formula["status_validacao"] = status if status in {"ok", "suspeita"} else "ok"

    eq_norm = normalize_formula_string(formula.get("equacao") or "")
    if "%%" in (formula.get("equacao") or "") or re.search(r"[A-Za-z]_?[A-Za-z0-9{}]*2$", eq_norm):
        formula["status_validacao"] = "suspeita"

    if is_normative_simple_assignment(formula.get("equacao") or "", formula.get("descricao")):
        formula["status_validacao"] = "ok"

    return formula


def split_formulas_and_graph_labels(
    formulas: list[dict],
    tipo_pagina: str,
    curvas_ou_rotulos: list[str] | None = None,
) -> tuple[list[dict], list[str]]:
    curvas = list(curvas_ou_rotulos or [])
    kept = []

    for formula in formulas:
        formula = normalize_formula_metadata(formula)
        if is_bad_delta_p_loss(formula, kept):
            continue
        if is_graph_label_formula(formula, tipo_pagina):
            label = (formula.get("equacao") or "").removeprefix("$$").removesuffix("$$").strip()
            if label and label not in curvas:
                curvas.append(label)
            continue
        kept.append(formula)

    return kept, curvas


def clean_formula_equation(equacao: str) -> str:
    if not equacao:
        return equacao

    body = equacao.strip().removeprefix("$$").removesuffix("$$").strip()
    body = body.replace("\t", " ")
    body = body.replace("`", "")
    if "$" in body:
        body = body.split("$", 1)[0].strip()
    body = re.split(r"\s*,\s*(?:e|onde|sendo)\b", body, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    body = re.split(r"\s+o coeficiente\b", body, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    body = re.sub(r"\\?text\s*\{[^{}]*\}", "", body)
    body = re.sub(r"\\?text\s*:[^)]*\)?", "", body)
    body = re.sub(r"\([^()]*\b(?:N/m|m/s|kg/m|Hz|anos?)\b[^()]*\)", "", body, flags=re.IGNORECASE)
    body = re.sub(r"\s+", " ", body).strip(" ;,.")

    if body and not body.startswith("$$"):
        body = "$$" + body
    if body and not body.endswith("$$"):
        body = body + "$$"
    return body


def strip_math_delimiters(equacao: str) -> str:
    return (equacao or "").strip().removeprefix("$$").removesuffix("$$").strip()


def trim_inline_formula_expr(expr: str) -> str:
    expr = (expr or "").strip("$ ")
    expr = re.sub(r"^(?:∆|Δ)\s*([A-Za-z])", r"\\Delta \1", expr)
    if "$" in expr:
        expr = expr.split("$", 1)[0].strip()
    expr = re.split(r"\s*,\s*(?:e|onde|sendo)\b", expr, maxsplit=1, flags=re.IGNORECASE)[0]
    expr = re.split(r"\s+(?:onde|sendo|expresso|em)\b", expr, maxsplit=1, flags=re.IGNORECASE)[0]
    expr = re.split(r"\s+o coeficiente\b", expr, maxsplit=1, flags=re.IGNORECASE)[0]
    return expr.strip(" ,;.")


def formula_description_from_context(text: str, start: int, expr: str) -> str:
    before = text[max(0, start - 180):start]
    before = re.sub(r"\s+", " ", before).strip(" :;,.")
    if before:
        for sep in [".", "\n", ";", ":"]:
            if sep in before:
                before = before.rsplit(sep, 1)[-1].strip(" :;,.")
        if before.startswith("$"):
            before = before.strip("$ ")
        if before.endswith("$"):
            before = before.strip("$ ")
        if "Consequentemente" in before and len(before) > 80:
            lhs = expr.split("=", 1)[0].strip()
            return f"Equação para determinar {lhs}" if lhs else "Fórmula extraída do texto teórico"
        if 8 <= len(before) <= 140 and not before.endswith("$"):
            return before

    lhs = expr.split("=", 1)[0].strip()
    if lhs:
        return f"Equação para determinar {lhs}"
    return "Fórmula extraída do texto teórico"


def extract_formulas_from_theoretical_text(texto_teorico: str | None) -> list[dict]:
    if not texto_teorico:
        return []

    formulas = []
    seen = set()

    for match in re.finditer(r"\$\$(.+?)\$\$", texto_teorico, flags=re.DOTALL):
        expr = re.sub(r"\s+", " ", match.group(1)).strip()
        if "=" not in expr:
            continue
        equacao = clean_formula_equation(f"$${expr}$$")
        key = normalize_formula_equivalence(equacao)
        if not key or key in seen:
            continue
        seen.add(key)
        formulas.append({
            "secao": None,
            "titulo_secao": None,
            "descricao": formula_description_from_context(texto_teorico, match.start(), expr),
            "equacao": equacao,
            "tipo_formula": "calculo",
            "origem": "texto_teorico",
            "status_validacao": "ok",
        })

    inline_pattern = re.compile(
        r"""
        (?P<expr>
            (?:(?:\\Delta|∆|Δ)\s*[A-Za-z](?:_[A-Za-z0-9{}]+)?|[A-Za-z][A-Za-z0-9_{}\\]*)
            \s*=\s*
            [^.;:\n]{1,90}
        )
        """,
        re.VERBOSE,
    )

    for match in inline_pattern.finditer(texto_teorico):
        expr = trim_inline_formula_expr(match.group("expr"))

        if not is_valid_formula_candidate("", expr):
            continue

        equacao = clean_formula_equation(f"$${expr}$$")
        key = normalize_formula_equivalence(equacao)
        if not key or key in seen:
            continue
        seen.add(key)

        formulas.append({
            "secao": None,
            "titulo_secao": None,
            "descricao": formula_description_from_context(texto_teorico, match.start(), expr),
            "equacao": equacao,
            "tipo_formula": "definicao" if classify_formula_type({"descricao": formula_description_from_context(texto_teorico, match.start(), expr), "equacao": equacao}) == "definicao" else "calculo",
            "origem": "texto_teorico",
            "status_validacao": "ok",
        })

    for match in re.finditer(r"\$([^$\n]{1,120}=[^$\n]{1,120})\$", texto_teorico):
        expr = trim_inline_formula_expr(match.group(1))

        if not is_valid_formula_candidate("", expr):
            continue

        equacao = clean_formula_equation(f"$${expr}$$")
        key = normalize_formula_equivalence(equacao)
        if not key or key in seen:
            continue
        seen.add(key)

        descricao = formula_description_from_context(texto_teorico, match.start(), expr)
        formulas.append({
            "secao": None,
            "titulo_secao": None,
            "descricao": descricao,
            "equacao": equacao,
            "tipo_formula": "definicao" if classify_formula_type({"descricao": descricao, "equacao": equacao}) == "definicao" else "calculo",
            "origem": "texto_teorico",
            "status_validacao": "ok",
        })

    return formulas


def merge_text_formulas(formulas: list[dict], text_formulas: list[dict]) -> list[dict]:
    merged = []
    seen_full = set()
    seen_lhs = set()

    for formula in formulas:
        formula = normalize_formula_metadata(formula)
        key = normalize_formula_equivalence(formula.get("equacao") or "")
        lhs = extract_formula_lhs(formula.get("equacao") or "")
        if key:
            seen_full.add(key)
        if lhs:
            seen_lhs.add(lhs)
        merged.append(formula)

    for formula in text_formulas:
        formula = normalize_formula_metadata(formula)
        key = normalize_formula_equivalence(formula.get("equacao") or "")
        lhs = extract_formula_lhs(formula.get("equacao") or "")
        if not key:
            continue
        if key in seen_full:
            continue
        if (
            lhs
            and lhs in seen_lhs
            and not is_normative_simple_assignment(formula.get("equacao") or "", formula.get("descricao"))
            and not should_allow_same_lhs_formula(formula, merged)
        ):
            continue
        merged.append(formula)
        seen_full.add(key)
        if lhs:
            seen_lhs.add(lhs)

    return merged


def should_allow_same_lhs_formula(formula: dict, existing_formulas: list[dict]) -> bool:
    lhs = extract_formula_lhs(formula.get("equacao") or "")
    key = normalize_formula_equivalence(formula.get("equacao") or "")
    if not lhs or not key:
        return False

    if lhs in {"q", "s1", "s2", "s3", "f", "deltap", "cpe", "cpi", "ce", "ci"}:
        for existing in existing_formulas:
            if normalize_formula_equivalence(existing.get("equacao") or "") == key:
                return False
        return True

    return False


def append_missing_formulas_to_text(texto_teorico: str | None, formulas: list[dict]) -> str | None:
    if not texto_teorico:
        return texto_teorico

    out = texto_teorico
    missing = []
    text_norm = normalize_formula_equivalence(texto_teorico)
    block_formula_keys = {
        normalize_formula_equivalence(f"$${match.group(1)}$$")
        for match in re.finditer(r"\$\$(.+?)\$\$", texto_teorico, flags=re.DOTALL)
    }

    for formula in formulas:
        equacao = (formula.get("equacao") or "").strip()
        if not equacao:
            continue

        eq_norm = normalize_formula_equivalence(equacao)
        if eq_norm and eq_norm not in text_norm and eq_norm not in block_formula_keys:
            inserted = insert_formula_near_context(out, formula)
            if inserted != out:
                out = inserted
                text_norm = normalize_formula_equivalence(out)
                continue
            missing.append(formula)

    if not missing:
        return out

    lines = [out.rstrip(), "", "### Formulas extraidas nesta pagina"]
    for formula in missing:
        descricao = formula.get("descricao") or "Formula extraida da pagina"
        formula_id = formula.get("formula_id") or ""
        lines.extend([
            "",
            f"- {descricao}",
            "",
            formula.get("equacao") or "",
            "",
            f"`formula_id: {formula_id}`",
        ])

    return "\n".join(lines).strip()


def insert_formula_near_context(texto_teorico: str, formula: dict) -> str:
    equacao = formula.get("equacao") or ""
    descricao = (formula.get("descricao") or "").strip()
    lhs = strip_math_delimiters(equacao).split("=", 1)[0].strip() if "=" in equacao else ""
    lhs_norm = normalize_formula_string(lhs)

    if not equacao or not lhs_norm:
        return texto_teorico

    lines = texto_teorico.splitlines()
    section = formula.get("secao")

    start_idx = 0
    if section:
        heading_re = re.compile(rf"^\s*#+\s+{re.escape(str(section))}\b")
        for idx, line in enumerate(lines):
            if heading_re.match(line):
                start_idx = idx
                break

    cue_words = [
        "pela expressão",
        "pela seguinte equação",
        "conforme a seguinte equação",
        "é obtida por",
        "é dada por",
        "portanto",
    ]

    best_idx = None
    for idx in range(start_idx, len(lines)):
        line = lines[idx].strip()
        if idx > start_idx and line.startswith("#"):
            break
        line_norm = normalize_for_text_match(line)
        if any(cue in line_norm for cue in cue_words):
            best_idx = idx
        if lhs_norm in normalize_formula_string(line) and "=" not in line:
            best_idx = idx

    if best_idx is None:
        return texto_teorico

    insert_at = best_idx + 1
    while insert_at < len(lines) and not lines[insert_at].strip():
        insert_at += 1

    if insert_at < len(lines) and lines[insert_at].strip().startswith("$$"):
        return texto_teorico

    lines[insert_at:insert_at] = ["", equacao, ""]
    return "\n".join(lines).strip()


def repair_formula_sections_by_text_position(
    formulas: list[dict],
    texto_teorico: str | None,
    raw_anterior: dict | None,
) -> list[dict]:
    if not formulas or not texto_teorico:
        return formulas

    section_positions = []
    for match in HEADER_CAPTURE_RE.finditer(texto_teorico):
        section_positions.append((match.start(), match.group(1).strip(), match.group(2).strip()))

    previous_section = None
    if raw_anterior:
        previous_section = raw_anterior.get("ultima_secao_detectada") or raw_anterior.get("secao_iniciada_na_pagina")

    for formula in formulas:
        descricao = (formula.get("descricao") or "").strip()
        equacao = (formula.get("equacao") or "").removeprefix("$$").removesuffix("$$").strip()
        eq_equiv = normalize_formula_equivalence(equacao)

        formula_pos = -1
        if equacao:
            formula_pos = texto_teorico.find(equacao)
        if formula_pos < 0 and eq_equiv:
            formula_pos = find_formula_position_by_equivalence(texto_teorico, eq_equiv)
        if formula_pos < 0 and descricao:
            formula_pos = texto_teorico.find(descricao)
        if formula_pos < 0:
            continue

        active_section = previous_section
        active_title = formula.get("titulo_secao")

        for heading_pos, section, title in section_positions:
            if heading_pos <= formula_pos:
                active_section = section
                active_title = normalize_inline_latex_in_titles(title)
            else:
                break

        if active_section:
            formula["secao"] = active_section
        if active_title:
            formula["titulo_secao"] = active_title

    return formulas


def find_formula_position_by_equivalence(texto_teorico: str, eq_equiv: str) -> int:
    if not texto_teorico or not eq_equiv:
        return -1

    for match in re.finditer(r"\$\$(.+?)\$\$|\$([^$\n]+)\$", texto_teorico, flags=re.DOTALL):
        expr = match.group(1) or match.group(2) or ""
        if normalize_formula_equivalence(expr) == eq_equiv:
            return match.start()

    lines = texto_teorico.splitlines()
    cursor = 0
    for line in lines:
        if normalize_formula_equivalence(line) == eq_equiv:
            return cursor
        cursor += len(line) + 1

    return -1


def merge_formula_candidates(
    formulas_gemini: list[dict],
    candidates_pdf: list[dict],
    pagina_real: str,
    secao_fallback: str | None,
    titulo_fallback: str | None,
) -> list[dict]:
    merged = []
    seen_full = set()
    seen_lhs = set()

    for idx, formula in enumerate(formulas_gemini, start=1):
        formula = ensure_formula_minimum_fields(
            formula=formula,
            pagina_real=pagina_real,
            idx=idx,
            secao_fallback=secao_fallback,
            titulo_fallback=titulo_fallback,
        )

        eq_norm = normalize_formula_string(formula.get("equacao", ""))
        lhs_norm = extract_formula_lhs(formula.get("equacao", ""))

        if eq_norm and eq_norm in seen_full:
            continue

        merged.append(formula)

        if eq_norm:
            seen_full.add(eq_norm)
        if lhs_norm:
            seen_lhs.add(lhs_norm)

    next_idx = len(merged) + 1

    for cand in candidates_pdf:
        eq = cand.get("equacao", "")
        desc = cand.get("descricao", "Fórmula detectada no texto da página")

        eq_norm = normalize_formula_string(eq)
        lhs_norm = extract_formula_lhs(eq)

        if not eq_norm:
            continue

        if eq_norm in seen_full:
            continue

        if lhs_norm and lhs_norm in seen_lhs:
            continue

        merged.append(
            ensure_formula_minimum_fields(
                formula={
                    "secao": secao_fallback,
                    "titulo_secao": titulo_fallback,
                    "descricao": desc,
                    "equacao": f"$${eq}$$",
                },
                pagina_real=pagina_real,
                idx=next_idx,
                secao_fallback=secao_fallback,
                titulo_fallback=titulo_fallback,
            )
        )

        seen_full.add(eq_norm)
        if lhs_norm:
            seen_lhs.add(lhs_norm)

        next_idx += 1

    return merged


# =========================================================
# TABELAS
# =========================================================
def table_has_meaningful_data(table_obj: dict) -> bool:
    if not isinstance(table_obj, dict):
        return False

    dados = table_obj.get("dados")
    if not dados:
        return False

    if isinstance(dados, dict):
        if not dados:
            return False

        for value in dados.values():
            if isinstance(value, list) and len(value) > 0:
                return True
            if isinstance(value, dict) and len(value) > 0:
                return True
            if isinstance(value, str) and value.strip():
                return True

    return False


def needs_table_refinement(tabelas: list[dict]) -> bool:
    if not tabelas:
        return False

    for tbl in tabelas:
        if not table_has_meaningful_data(tbl):
            return True
        dados = tbl.get("dados") or {}
        headers = dados.get("headers") or []
        rows = dados.get("rows") or []
        if headers and rows:
            row_lengths = {len(row) for row in rows if isinstance(row, list)}
            if len(row_lengths) > 1:
                return True
            if row_lengths and len(headers) != next(iter(row_lengths)):
                return True

    return False


def extract_tables_only(img_bytes: bytes, raw_text: str, contexto_anterior: str) -> list[dict]:
    prompt_final = f"""
{PROMPT_TABELA_ESPECIALIZADO}

CONTEXTO DA PÁGINA ANTERIOR:
{contexto_anterior}

TEXTO BRUTO EXTRAÍDO DIRETAMENTE DO PDF:
{raw_text}

INSTRUÇÃO ADICIONAL:
Extraia apenas a tabela desta página.
Se houver conteúdo legível na tabela, não deixe o campo "dados" vazio.
Se houver cabecalho hierarquico, combine os niveis em nomes finais de coluna.
Exemplo: Categoria I / Classe A vira "I_A"; Categoria V / Classe C vira "V_C".
O numero de headers deve ser igual ao numero de celulas de cada row.
Nao crie coluna "Categoria" quando ela for apenas rotulo agrupador das categorias I a V.
""".strip()

    data = call_gemini_json(prompt_final, img_bytes)
    return data.get("tabelas") or []


def compact_header_token(value: str) -> str:
    value = str(value or "").strip()
    value = re.sub(r"\s+", " ", value)
    value = value.replace("$", "")
    value = value.replace("{", "").replace("}", "")
    return value


def normalize_table_headers_to_rows(table: dict) -> dict:
    dados = table.get("dados")
    if not isinstance(dados, dict):
        return table

    headers = dados.get("headers") or []
    rows = dados.get("rows") or []
    if not headers or not rows:
        return table

    row_lengths = [len(row) for row in rows if isinstance(row, list)]
    if not row_lengths:
        return table

    most_common_len = max(set(row_lengths), key=row_lengths.count)
    title = table.get("titulo") or ""
    normalized_title = normalize_formula_string(title)
    header_tokens = [compact_header_token(h) for h in headers]

    if "tabela3" in normalized_title or "fators2" in normalized_title:
        if most_common_len == 16:
            dados["headers"] = [
                "z_m",
                "I_A", "I_B", "I_C",
                "II_A", "II_B", "II_C",
                "III_A", "III_B", "III_C",
                "IV_A", "IV_B", "IV_C",
                "V_A", "V_B", "V_C",
            ]
            normalize_row_lengths(dados)
        return table

    if "tabela5" in normalized_title or ("zg" in normalized_title and "z0" in normalized_title):
        if most_common_len == 6:
            dados["headers"] = ["Parâmetro", "I", "II", "III", "IV", "V"]
            normalize_row_lengths(dados)
        return table

    if len(headers) != most_common_len:
        if "Categoria" in header_tokens and set(["I", "II", "III", "IV", "V"]).issubset(set(header_tokens)):
            dados["headers"] = ["Parâmetro", "I", "II", "III", "IV", "V"][:most_common_len]
        else:
            dados["headers"] = [f"col_{idx}" for idx in range(1, most_common_len + 1)]

    normalize_row_lengths(dados)
    return table


def normalize_row_lengths(dados: dict) -> None:
    headers = dados.get("headers") or []
    rows = dados.get("rows") or []
    if not headers or not rows:
        return

    target = len(headers)
    fixed_rows = []
    for row in rows:
        if not isinstance(row, list):
            fixed_rows.append(row)
            continue
        if len(row) < target:
            fixed_rows.append(row + [""] * (target - len(row)))
        elif len(row) > target:
            fixed_rows.append(row[:target])
        else:
            fixed_rows.append(row)
    dados["rows"] = fixed_rows


def get_table_shape(table: dict) -> tuple[dict | None, list, list, int]:
    dados = table.get("dados")
    if not isinstance(dados, dict):
        return None, [], [], 0

    headers = dados.get("headers") or []
    rows = dados.get("rows") or []
    if not headers or not rows:
        return dados, headers, rows, 0

    row_lengths = [len(row) for row in rows if isinstance(row, list)]
    if not row_lengths:
        return dados, headers, rows, 0

    return dados, headers, rows, max(set(row_lengths), key=row_lengths.count)


def table_text_signature(table: dict, headers: list, rows: list) -> str:
    title = table.get("titulo") or ""
    sample_rows = rows[:5] if rows else []
    raw = " ".join(
        [title]
        + [str(h) for h in headers]
        + [str(cell) for row in sample_rows if isinstance(row, list) for cell in row]
    )
    return normalize_formula_string(raw)


def normalize_category_class_table(table: dict) -> bool:
    dados, headers, rows, most_common_len = get_table_shape(table)
    if not dados or not most_common_len:
        return False

    signature = table_text_signature(table, headers, rows)
    has_categories = all(cat in signature for cat in ["i", "ii", "iii", "iv", "v"])
    has_classes = all(cls in signature for cls in ["a", "b", "c"])
    has_height_axis = "zm" in signature or "z(m)" in signature or "altura" in signature

    if not (has_categories and has_classes and has_height_axis and most_common_len == 16):
        return False

    dados["headers"] = [
        "z_m",
        "I_A", "I_B", "I_C",
        "II_A", "II_B", "II_C",
        "III_A", "III_B", "III_C",
        "IV_A", "IV_B", "IV_C",
        "V_A", "V_B", "V_C",
    ]
    normalize_row_lengths(dados)
    return True


def normalize_parameter_category_table(table: dict) -> bool:
    dados, headers, rows, most_common_len = get_table_shape(table)
    if not dados or not most_common_len:
        return False

    signature = table_text_signature(table, headers, rows)
    has_categories = all(cat in signature for cat in ["i", "ii", "iii", "iv", "v"])
    first_cells = [str(row[0]).strip() for row in rows if isinstance(row, list) and row]
    looks_parameter_based = (
        any("param" in compact_header_token(h).lower() for h in headers)
        or any(normalize_formula_string(cell) in {"zg(m)", "z0(m)", "zg", "z0"} for cell in first_cells)
    )

    if not (has_categories and looks_parameter_based and most_common_len == 6):
        return False

    dados["headers"] = ["Parâmetro", "I", "II", "III", "IV", "V"]
    normalize_row_lengths(dados)
    return True


def normalize_group_factor_table(table: dict) -> bool:
    dados, headers, rows, most_common_len = get_table_shape(table)
    if not dados or not most_common_len:
        return False

    signature = table_text_signature(table, headers, rows)
    header_text = " ".join(str(h).lower() for h in headers)
    has_group = "grupo" in signature
    has_description = "descricao" in signature or "descrição" in header_text
    has_factor = "s3" in signature or "fator" in signature
    has_period = "tp" in signature or "anos" in signature

    if not (has_group and has_description and has_factor and has_period and most_common_len == 4):
        return False

    dados["headers"] = ["Grupo", "Descrição", "$S_3$", "$T_p$ (anos)"]
    normalize_row_lengths(dados)
    return True


def normalize_generic_table_shape(table: dict) -> bool:
    dados, headers, rows, most_common_len = get_table_shape(table)
    if not dados or not most_common_len:
        return False

    if len(headers) == most_common_len:
        normalize_row_lengths(dados)
        return True

    header_tokens = [compact_header_token(h) for h in headers]
    if "Categoria" in header_tokens and set(["I", "II", "III", "IV", "V"]).issubset(set(header_tokens)):
        dados["headers"] = ["Parâmetro", "I", "II", "III", "IV", "V"][:most_common_len]
    else:
        dados["headers"] = [f"col_{idx}" for idx in range(1, most_common_len + 1)]

    normalize_row_lengths(dados)
    return True


def normalize_table_headers_to_rows(table: dict) -> dict:
    for normalizer in [
        normalize_category_class_table,
        normalize_parameter_category_table,
        normalize_group_factor_table,
        normalize_generic_table_shape,
    ]:
        if normalizer(table):
            break

    return table


def normalize_tables(tabelas: list[dict]) -> list[dict]:
    normalized = []
    for tabela in tabelas:
        if tabela.get("titulo"):
            tabela["titulo"] = normalize_inline_latex_in_titles(tabela["titulo"])
        normalized.append(normalize_table_headers_to_rows(tabela))
    return normalized


# =========================================================
# GEMINI
# =========================================================
def call_gemini_json(prompt: str, img_bytes: bytes) -> dict:
    max_attempts = int(os.getenv("GEMINI_MAX_RETRIES", "4"))
    base_delay = float(os.getenv("GEMINI_RETRY_BASE_DELAY", "12"))

    for attempt in range(1, max_attempts + 1):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=[
                    prompt,
                    types.Part.from_bytes(data=img_bytes, mime_type="image/png"),
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )
            break
        except Exception as e:
            message = str(e)
            is_retryable = "429" in message or "RESOURCE_EXHAUSTED" in message
            if not is_retryable or attempt == max_attempts:
                raise

            delay = base_delay * attempt
            print(f"  -> limite da API Gemini atingido; nova tentativa em {delay:.0f}s ({attempt}/{max_attempts})")
            time.sleep(delay)

    texto_bruto = response.text
    texto_limpo = limpar_json_quebrado(texto_bruto)
    return json.loads(texto_limpo)


# =========================================================
# EXTRAÇÃO PRINCIPAL
# =========================================================
def processar_pagina(
    doc: fitz.Document,
    page_index: int,
    output_dir: Path,
    raw_anterior: dict | None = None,
    dpi: int = 170,
) -> dict:
    num_pdf = page_index + 1
    print(f"\n--- Analisando página PDF {num_pdf} ---")

    page = doc.load_page(page_index)
    pix = page.get_pixmap(dpi=dpi)
    img_bytes = pix.tobytes("png")

    raw_text = extract_pdf_text(page)
    formula_candidates = extract_formula_candidates(raw_text)
    contexto_anterior = resumir_contexto_anterior(raw_anterior)

    prompt_final = f"""
{PROMPT_ESTRUTURADO}

CONTEXTO DA PÁGINA ANTERIOR:
{contexto_anterior}

TEXTO BRUTO EXTRAÍDO DIRETAMENTE DO PDF:
{raw_text}

FÓRMULAS CANDIDATAS DETECTADAS AUTOMATICAMENTE NO TEXTO:
{json.dumps(formula_candidates, ensure_ascii=False, indent=2)}

INSTRUÇÃO ADICIONAL:
Use o texto bruto como base principal.
Use a imagem para confirmar headings, fórmulas, tabelas e legenda de figura.
Se uma fórmula aparecer no texto bruto ou nas fórmulas candidatas e estiver realmente presente na página, ela deve ser salva no campo "formulas".
Preserve formulas tambem dentro de "texto_teorico", no ponto aproximado onde aparecem, usando bloco LaTeX $$...$$.
Preencha "tipo_pagina" com texto_normativo, nomenclatura, figura_grafico, tabela ou mista.
Para cada formula, preencha tipo_formula, origem e status_validacao.
Aceite formulas inline de definicao, como "coeficiente de arrasto; C_a = F_a/(q A)".
Nao coloque rotulos de curvas/eixos de graficos em "formulas"; coloque em "curvas_ou_rotulos".
A secao da formula deve ser a secao imediatamente anterior a ela no fluxo da pagina.
Extraia somente o que aparece nesta página atual.
""".strip()

    try:
        dados = call_gemini_json(prompt_final, img_bytes)
    except Exception as e:
        erro_path = output_dir / "erros" / f"erro_pag_pdf_{num_pdf}.txt"
        erro_path.parent.mkdir(parents=True, exist_ok=True)
        erro_path.write_text(str(e), encoding="utf-8")
        raise

    pagina_real = normalizar_pagina_real(
        dados.get("numero_pagina_impresso"),
        fallback_pdf_num=num_pdf
    )

    texto_teorico = dados.get("texto_teorico")
    if texto_teorico:
        texto_teorico = clean_textual_leakage(texto_teorico)
        texto_teorico = recover_raw_top_continuation(texto_teorico, raw_text)
        texto_teorico = normalize_markdown_headings(texto_teorico)
        texto_teorico = normalize_inline_variables(texto_teorico)

    secao_fallback = dados.get("ultima_secao_detectada") or dados.get("secao_iniciada_na_pagina")
    titulo_fallback = None

    if texto_teorico:
        _sec_num, _sec_title = extract_last_section_from_text(texto_teorico)
        if _sec_title:
            titulo_fallback = _sec_title

    tipo_pagina = infer_page_type(dados, texto_teorico, raw_text)

    formulas = merge_formula_candidates(
        formulas_gemini=dados.get("formulas") or [],
        candidates_pdf=formula_candidates,
        pagina_real=pagina_real,
        secao_fallback=secao_fallback,
        titulo_fallback=titulo_fallback,
    )

    formulas = repair_formula_sections_by_text_position(
        formulas=formulas,
        texto_teorico=texto_teorico,
        raw_anterior=raw_anterior,
    )
    formulas = merge_text_formulas(
        formulas=formulas,
        text_formulas=extract_formulas_from_theoretical_text(texto_teorico),
    )
    formulas = repair_formula_sections_by_text_position(
        formulas=formulas,
        texto_teorico=texto_teorico,
        raw_anterior=raw_anterior,
    )
    formulas = prune_redundant_formulas(formulas)
    formulas, curvas_ou_rotulos = split_formulas_and_graph_labels(
        formulas=formulas,
        tipo_pagina=tipo_pagina,
        curvas_ou_rotulos=dados.get("curvas_ou_rotulos") or [],
    )
    formulas = reindex_formulas(formulas, pagina_real)
    texto_teorico = append_missing_formulas_to_text(texto_teorico, formulas)

    tabelas_finais = dados.get("tabelas") or []

    if needs_table_refinement(tabelas_finais):
        try:
            tabelas_refinadas = extract_tables_only(
                img_bytes=img_bytes,
                raw_text=raw_text,
                contexto_anterior=contexto_anterior,
            )
            if tabelas_refinadas:
                tabelas_finais = tabelas_refinadas
                print("  -> tabela refinada com chamada especializada")
        except Exception as e:
            print(f"  -> falha no refinamento de tabela: {e}")

    tabelas_finais = normalize_tables(tabelas_finais)
    texto_teorico = remove_structured_table_from_text(texto_teorico, tabelas_finais)
    tipo_pagina = infer_page_type(
        {**dados, "tabelas": tabelas_finais},
        texto_teorico,
        raw_text,
    )

    dados_final = {
        "numero_pagina_impresso": pagina_real,
        "tipo_pagina": tipo_pagina,
        "secao_iniciada_na_pagina": dados.get("secao_iniciada_na_pagina"),
        "ultima_secao_detectada": dados.get("ultima_secao_detectada"),
        "secao_continua_na_proxima": dados.get("secao_continua_na_proxima", False),
        "texto_teorico": texto_teorico,
        "tabelas": tabelas_finais,
        "formulas": formulas,
        "figura_legenda": normalize_inline_latex_in_titles(dados.get("figura_legenda")),
        "curvas_ou_rotulos": curvas_ou_rotulos,
    }

    print(f"✔ Página impressa identificada: {pagina_real}")
    print(f"  -> tipo de página: {tipo_pagina}")
    print(f"  -> fórmulas candidatas detectadas no PDF: {len(formula_candidates)}")
    print(f"  -> fórmulas finais salvas: {len(formulas)}")
    if curvas_ou_rotulos:
        print(f"  -> rótulos/curvas de gráfico: {len(curvas_ou_rotulos)}")

    dir_textos = output_dir / "textos"
    dir_tabelas = output_dir / "tabelas"
    dir_formulas = output_dir / "formulas"
    dir_figuras = output_dir / "figuras"
    dir_raw = output_dir / "raw_paginas"

    if SAVE_RAW_DEBUG:
        salvar_json(dir_raw / f"pag_{pagina_real}_raw.json", dados_final)

    if dados_final["texto_teorico"]:
        dir_textos.mkdir(parents=True, exist_ok=True)
        with open(dir_textos / f"pag_{pagina_real}_teoria.md", "w", encoding="utf-8") as f:
            f.write(dados_final["texto_teorico"])
        print("  -> texto salvo")

    for idx, tabela in enumerate(dados_final["tabelas"], start=1):
        salvar_json(dir_tabelas / f"pag_{pagina_real}_tabela_{idx}.json", tabela)
    if dados_final["tabelas"]:
        print(f"  -> {len(dados_final['tabelas'])} tabela(s) salva(s)")

    for idx, formula in enumerate(dados_final["formulas"], start=1):
        salvar_json(dir_formulas / f"pag_{pagina_real}_formula_{idx}.json", formula)
    if dados_final["formulas"]:
        print(f"  -> {len(dados_final['formulas'])} fórmula(s) salva(s)")

    if dados_final["figura_legenda"]:
        salvar_json(
            dir_figuras / f"pag_{pagina_real}_figura.json",
            {
                "figura_legenda": dados_final["figura_legenda"],
                "curvas_ou_rotulos": dados_final["curvas_ou_rotulos"],
            }
        )
        print("  -> figura/legenda salva")

    return dados_final


def processar_pdf(
    pdf_path: str | Path,
    output_dir: str | Path,
    pdf_start: int | None = None,
    pdf_end: int | None = None,
    dpi: int = 170,
):
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF não encontrado: {pdf_path}")

    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Abrindo arquivo: {pdf_path}")
    doc = fitz.open(pdf_path)

    total_paginas = len(doc)
    start_idx = 0 if pdf_start is None else max(pdf_start - 1, 0)
    end_idx = total_paginas - 1 if pdf_end is None else min(pdf_end - 1, total_paginas - 1)

    if start_idx > end_idx:
        raise ValueError("Intervalo de páginas inválido.")

    raw_anterior = None

    for page_index in range(start_idx, end_idx + 1):
        try:
            raw_atual = processar_pagina(
                doc=doc,
                page_index=page_index,
                output_dir=output_dir,
                raw_anterior=raw_anterior,
                dpi=dpi,
            )
            raw_anterior = raw_atual
        except Exception as e:
            print(f"❌ Erro ao processar página PDF {page_index + 1}: {e}")
            raw_anterior = None

    print("\n✅ Processamento finalizado.")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Extrai paginas da NBR 6123 com Gemini."
    )
    parser.add_argument(
        "--pdf",
        default=str(BASE_DIR / "knowledge_base" / "normas" / "NBR6123.pdf"),
        help="Caminho do PDF a processar.",
    )
    parser.add_argument(
        "--output",
        default=str(BASE_DIR / "knowledge_base" / "extraidos"),
        help="Diretorio de saida dos arquivos extraidos.",
    )
    parser.add_argument(
        "--start",
        type=int,
        default=1,
        help="Pagina PDF inicial, comecando em 1.",
    )
    parser.add_argument(
        "--end",
        type=int,
        default=None,
        help="Pagina PDF final, inclusiva. Se omitida, processa ate o fim do PDF.",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=170,
        help="Resolucao usada para renderizar cada pagina como imagem.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    processar_pdf(
        pdf_path=args.pdf,
        output_dir=args.output,
        pdf_start=args.start,
        pdf_end=args.end,
        dpi=args.dpi,
    )
