from __future__ import annotations

from app.orchestrator.intent_router import build_orchestration_plan
from app.orchestrator.schemas import OrchestrationPlan
from app.tools.registry import ToolRegistry, build_default_tool_registry


class ChatOrchestrator:
    """Builds a technical execution plan without owning the current response flow.

    The existing RagChatService remains the production facade. This class is the
    stable place to evolve tool routing, logging, MCP exposure and persistence
    without forcing the Flask routes to change.
    """

    def __init__(self, tool_registry: ToolRegistry | None = None) -> None:
        self.tool_registry = tool_registry or build_default_tool_registry()

    def plan(self, question: str) -> OrchestrationPlan:
        plan = build_orchestration_plan(question)
        missing_tools = [tool for tool in plan.tools if not self.tool_registry.has(tool)]
        if not missing_tools:
            return plan
        return OrchestrationPlan(
            intent=plan.intent,
            confidence=plan.confidence,
            route=plan.route,
            tools=plan.tools,
            collections=plan.collections,
            response_mode=plan.response_mode,
            needs_llm=plan.needs_llm,
            reasons=plan.reasons,
            warnings=plan.warnings + [f"Ferramentas nao registradas: {', '.join(missing_tools)}"],
        )

    def describe_tools(self) -> list[dict]:
        return self.tool_registry.describe()

