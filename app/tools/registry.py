from __future__ import annotations

from typing import Any

from app.rag.normative_map import guidance_for_intent
from app.tools.contracts import RegisteredTool, ToolContract, ToolParameter, ToolResult


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(self, tool: RegisteredTool) -> None:
        if tool.name in self._tools:
            raise ToolRegistryError(f"Ferramenta ja registrada: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> RegisteredTool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ToolRegistryError(f"Ferramenta nao encontrada: {name}") from exc

    def names(self) -> list[str]:
        return sorted(self._tools)

    def describe(self) -> list[dict[str, Any]]:
        return [self._tools[name].describe() for name in self.names()]

    def has(self, name: str) -> bool:
        return name in self._tools


class ToolRegistryError(Exception):
    pass


def _normative_flow_handler(intent: str = "orientacao_normativa", **_: Any) -> ToolResult:
    guidance = guidance_for_intent(intent) or guidance_for_intent("orientacao_normativa")
    return ToolResult(
        ok=bool(guidance),
        tool_name="get_normative_flow",
        data={"intent": intent, "flow": guidance},
        markdown=guidance,
        sources=[{
            "fonte": "Mapa normativo interno",
            "secao": "fluxo principal",
            "tipo_conteudo": "orientacao",
        }],
    )


def build_default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()

    registry.register(RegisteredTool(
        contract=ToolContract(
            name="search_norma",
            description="Busca trechos estruturados da ABNT NBR 6123 na base vetorial/lexical.",
            category="retrieval",
            input_schema=[
                ToolParameter("query", "string", "Pergunta ou consulta tecnica."),
                ToolParameter("content_types", "list[string]", "Tipos desejados: texto, formula, tabela ou figura.", False),
            ],
            output_schema=[
                ToolParameter("items", "list[object]", "Trechos recuperados com metadados."),
                ToolParameter("sources", "list[object]", "Fontes normativas usadas."),
            ],
            sources=["knowledge_base/processado/norma", "ChromaDB:nbr6123_norma"],
            safety_notes=["Nao deve inventar valores; apenas recuperar trechos indexados."],
        ),
    ))

    registry.register(RegisteredTool(
        contract=ToolContract(
            name="search_articles",
            description="Busca artigos tecnicos complementares, separados da colecao normativa.",
            category="retrieval",
            input_schema=[ToolParameter("query", "string", "Consulta sobre artigo, proposta ou comparacao.")],
            output_schema=[ToolParameter("items", "list[object]", "Trechos de artigos com metadados.")],
            sources=["knowledge_base/processado/artigos", "ChromaDB:ventos_artigos"],
            safety_notes=["Artigos podem complementar, mas nao substituem a NBR."],
        ),
    ))

    registry.register(RegisteredTool(
        contract=ToolContract(
            name="lookup_v0",
            description="Consulta a velocidade basica do vento V0 por cidade/UF ou coordenadas.",
            category="location",
            input_schema=[
                ToolParameter("message", "string", "Mensagem original do usuario com localizacao."),
            ],
            output_schema=[
                ToolParameter("v0", "number|null", "Velocidade basica do vento em m/s quando encontrada.", False),
                ToolParameter("location", "object", "Localizacao extraida."),
                ToolParameter("sources", "list[object]", "Fonte do mapa de isopletas."),
            ],
            sources=["Mapa de isopletas da NBR 6123"],
            safety_notes=["Nao aproximar V0 quando a ferramenta indicar cidade ambigua ou zona especial."],
        ),
    ))

    registry.register(RegisteredTool(
        contract=ToolContract(
            name="calculate_wind",
            description="Executa calculos determinísticos de vento ja suportados pelo motor Python.",
            category="calculation",
            input_schema=[ToolParameter("question", "string", "Pergunta com dados numericos do calculo.")],
            output_schema=[
                ToolParameter("operation", "string", "Operacao calculada."),
                ToolParameter("values", "object", "Valores usados e resultados."),
                ToolParameter("missing", "list[string]", "Dados faltantes quando houver.", False),
            ],
            sources=["app/calculos", "NBR 6123"],
            safety_notes=["A LLM deve redigir; o Python deve calcular."],
        ),
    ))

    registry.register(RegisteredTool(
        contract=ToolContract(
            name="get_normative_flow",
            description="Fornece o fluxo principal de orientacao normativa da NBR 6123.",
            category="normative_guidance",
            input_schema=[ToolParameter("intent", "string", "Intencao tecnica detectada.", False)],
            output_schema=[ToolParameter("flow", "string", "Fluxo orientativo V0 -> Vk -> q -> pressoes/forcas.")],
            sources=["app/rag/normative_map.py"],
            safety_notes=["Serve como orientacao; detalhes devem ser confirmados no RAG."],
        ),
        handler=_normative_flow_handler,
    ))

    return registry
