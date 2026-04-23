from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class OrchestrationPlan:
    intent: str
    confidence: float
    route: str
    tools: list[str] = field(default_factory=list)
    collections: list[str] = field(default_factory=list)
    response_mode: str = "tecnico"
    needs_llm: bool = True
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    selection: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
