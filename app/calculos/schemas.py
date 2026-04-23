from dataclasses import dataclass, field
from typing import Any


@dataclass
class CalculationResult:
    handled: bool
    operation: str = ""
    markdown: str = ""
    missing: list[str] = field(default_factory=list)
    values: dict[str, Any] = field(default_factory=dict)
    sources: list[dict[str, str]] = field(default_factory=list)

    @property
    def needs_user_data(self) -> bool:
        return bool(self.missing)
