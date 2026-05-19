from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pm_assistant.core.models import Evidence, FeatureConfig


@dataclass(slots=True)
class ConnectorResult:
    evidence: list[Evidence] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class Connector:
    name = "base"

    def doctor(self) -> ConnectorResult:
        raise NotImplementedError

    def collect(self, config: FeatureConfig, date_range: str | None = None) -> ConnectorResult:
        raise NotImplementedError
