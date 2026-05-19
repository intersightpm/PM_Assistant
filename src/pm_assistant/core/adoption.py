from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pm_assistant.connectors import intersight
from pm_assistant.connectors.snowflake import list_query_templates, run_query_template


def collect_adoption_signals(
    topic: str,
    sources: list[str],
    account: str = "all",
    snowflake_template: str | None = None,
    max_rows: int = 100,
) -> dict[str, Any]:
    normalized_sources = [source.strip().lower() for source in sources if source.strip()]
    source_signals: dict[str, Any] = {}
    warnings: list[str] = []
    known_gaps: list[str] = []
    metric_candidates: dict[str, Any] = {}

    if "snowflake" in normalized_sources:
        try:
            template = snowflake_template or default_snowflake_template()
            result = run_query_template(template, max_rows=max_rows)
            source_signals["snowflake"] = {"query_template": template, "result": result}
            metric_candidates["snowflake_rows"] = result.get("row_count")
            metric_candidates["snowflake_columns"] = result.get("columns", [])
        except Exception as exc:
            warnings.append(f"snowflake: {exc}")
            known_gaps.append("Snowflake adoption metrics are not available from this run.")

    if "intersight" in normalized_sources:
        try:
            signal = intersight.adoption_signals(topic, account=account)
            source_signals["intersight"] = signal
            metric_candidates["intersight_managed_assets"] = signal.get("signals", {}).get("managed_assets", {})
            metric_candidates["intersight_health_friction"] = signal.get("signals", {}).get("health_friction", {})
            warnings.extend(signal.get("warnings", []))
        except Exception as exc:
            warnings.append(f"intersight: {exc}")
            known_gaps.append("Intersight inventory/health signals are not available from this run.")

    for source in normalized_sources:
        if source not in {"snowflake", "intersight"}:
            warnings.append(f"{source}: unsupported adoption source")
            known_gaps.append(f"{source} adoption signals are not implemented.")

    return {
        "schema_version": 1,
        "artifact_type": "adoption_signals",
        "topic": topic,
        "created_at": utc_now_iso(),
        "sources": normalized_sources,
        "source_signals": source_signals,
        "metric_candidates": metric_candidates,
        "warnings": warnings,
        "known_gaps": known_gaps,
    }


def default_snowflake_template() -> str:
    templates = list_query_templates()
    for candidate in ("Adoption.sql", "Adoption_withCustomerCounts.sql"):
        if candidate in templates:
            return candidate
    if not templates:
        raise FileNotFoundError("No Snowflake query templates found.")
    return templates[0]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
