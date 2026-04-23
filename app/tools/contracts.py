from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Literal


ToolCategory = Literal[
    "retrieval",
    "calculation",
    "location",
    "normative_guidance",
    "response",
]


@dataclass(frozen=True)
class ToolParameter:
    name: str
    type: str
    description: str
    required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ToolContract:
    name: str
    description: str
    category: ToolCategory
    input_schema: list[ToolParameter] = field(default_factory=list)
    output_schema: list[ToolParameter] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    safety_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "input_schema": [param.to_dict() for param in self.input_schema],
            "output_schema": [param.to_dict() for param in self.output_schema],
            "sources": list(self.sources),
            "safety_notes": list(self.safety_notes),
        }


@dataclass
class ToolResult:
    ok: bool
    tool_name: str
    data: dict[str, Any] = field(default_factory=dict)
    markdown: str = ""
    sources: list[dict[str, Any]] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "tool_name": self.tool_name,
            "data": self.data,
            "markdown": self.markdown,
            "sources": self.sources,
            "missing": self.missing,
            "error": self.error,
        }


ToolHandler = Callable[..., ToolResult]


@dataclass
class RegisteredTool:
    contract: ToolContract
    handler: ToolHandler | None = None

    @property
    def name(self) -> str:
        return self.contract.name

    def describe(self) -> dict[str, Any]:
        return self.contract.to_dict()

    def run(self, **kwargs: Any) -> ToolResult:
        if self.handler is None:
            return ToolResult(
                ok=False,
                tool_name=self.name,
                error="Ferramenta registrada apenas como contrato; handler nao conectado.",
            )
        return self.handler(**kwargs)

