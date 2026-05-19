from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(slots=True)
class Evidence:
    id: str
    source: str
    source_type: str
    title: str
    text: str
    author: str = ""
    requester: str = ""
    created_at: str = ""
    updated_at: str = ""
    url: str = ""
    raw_excerpt: str = ""
    source_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if not data["raw_excerpt"]:
            data["raw_excerpt"] = self.text[:800]
        return data


@dataclass(slots=True)
class FeatureConfig:
    feature_name: str
    aliases: list[str] = field(default_factory=list)
    related_terms: list[str] = field(default_factory=list)
    exclude_terms: list[str] = field(default_factory=list)
    related_terms_match_without_feature: bool = False
    source_filters: dict[str, Any] = field(default_factory=dict)
    category_hints: list[str] = field(default_factory=list)
    report: dict[str, Any] = field(default_factory=dict)

    def all_positive_terms(self) -> list[str]:
        terms = [self.feature_name, *self.aliases, *self.related_terms]
        seen: set[str] = set()
        cleaned: list[str] = []
        for term in terms:
            normalized = " ".join(str(term).strip().lower().split())
            if normalized and normalized not in seen:
                cleaned.append(normalized)
                seen.add(normalized)
        return cleaned

    def anchor_terms(self) -> list[str]:
        terms = [self.feature_name, *self.aliases]
        seen: set[str] = set()
        cleaned: list[str] = []
        for term in terms:
            normalized = " ".join(str(term).strip().lower().split())
            if normalized and normalized not in seen:
                cleaned.append(normalized)
                seen.add(normalized)
        return cleaned


@dataclass(slots=True)
class RunResult:
    run_id: str
    feature_name: str
    created_at: str
    sources: list[str]
    evidence: list[Evidence]
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "feature_name": self.feature_name,
            "created_at": self.created_at,
            "sources": self.sources,
            "warnings": self.warnings,
            "metadata": self.metadata,
            "evidence": [item.to_dict() for item in self.evidence],
        }
