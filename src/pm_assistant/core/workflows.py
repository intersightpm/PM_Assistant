from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pm_assistant.connectors.registry import get_connector

from .config import load_environment, load_feature_config
from .matching import dedupe_evidence, filter_evidence, score_text
from .models import RunResult
from .storage import evidence_from_dict, latest_run_id, load_run, save_run, save_source_checkpoint


def make_run_id(feature_name: str) -> str:
    slug = "-".join(feature_name.lower().replace("_", "-").split())
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{slug}-{stamp}"


def collect_evidence(feature_name: str, sources: list[str], config_path: str | None = None, date_range: str | None = None) -> RunResult:
    load_environment()
    config = load_feature_config(feature_name, config_path)
    run_id = make_run_id(feature_name)
    created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    warnings: list[str] = []
    evidence = []
    source_metadata: dict[str, dict] = {}
    run_metadata = {"collection_profile": str(config.source_filters.get("collection_profile") or "accuracy"), "sources": source_metadata, "status": "partial"}
    print(f"[collect] run {run_id}: starting sources {', '.join(sources)}", flush=True)
    for source_number, source in enumerate(sources, start=1):
        print(f"[collect] run {run_id}: collecting {source} ({source_number}/{len(sources)})", flush=True)
        connector = get_connector(source)
        try:
            result = connector.collect(config, date_range=date_range)
        except Exception as exc:
            warnings.append(f"{source}: collection failed: {exc}")
            source_metadata[source] = {"status": "failed", "error": str(exc)}
            save_source_checkpoint(run_id, source, {
                "run_id": run_id,
                "feature_name": feature_name,
                "created_at": created_at,
                "source": source,
                "warnings": [f"{source}: collection failed: {exc}"],
                "metadata": source_metadata[source],
                "evidence": [],
            })
            save_run(RunResult(
                run_id=run_id, feature_name=feature_name, created_at=created_at,
                sources=sources[:source_number], evidence=dedupe_evidence(filter_evidence(evidence, config)), warnings=warnings,
                metadata=run_metadata))
            print(f"[collect] run {run_id}: {source} failed; saved partial run", flush=True)
            continue
        evidence.extend(result.evidence)
        warnings.extend(f"{source}: {warning}" for warning in result.warnings)
        source_metadata[source] = dict(result.metadata or {})
        filtered = dedupe_evidence(filter_evidence(evidence, config))
        partial = RunResult(
            run_id=run_id, feature_name=feature_name, created_at=created_at,
            sources=sources[:source_number], evidence=filtered, warnings=warnings, metadata=run_metadata)
        save_source_checkpoint(run_id, source, {
            "run_id": run_id,
            "feature_name": feature_name,
            "created_at": created_at,
            "source": source,
            "warnings": [f"{source}: {warning}" for warning in result.warnings],
            "metadata": result.metadata,
            "evidence": [item.to_dict() for item in result.evidence],
        })
        save_run(partial)
        print(
            f"[collect] run {run_id}: completed {source}; source evidence={len(result.evidence)}, "
            f"combined evidence={len(filtered)}, warnings={len(warnings)}",
            flush=True,
        )
    evidence = dedupe_evidence(filter_evidence(evidence, config))
    run_metadata["status"] = "completed"
    run = RunResult(run_id=run_id, feature_name=feature_name, created_at=created_at, sources=sources, evidence=evidence, warnings=warnings, metadata=run_metadata)
    save_run(run)
    print(f"[collect] run {run_id}: saved final evidence={len(evidence)}, warnings={len(warnings)}", flush=True)
    return run


def run_doctor(sources: list[str]) -> dict:
    load_environment()
    results: dict[str, list[str]] = {}
    for source in sources:
        connector = get_connector(source)
        results[source] = connector.doctor().warnings
    return results


def search_run(query: str, run_id: str | None = None, sources: list[str] | None = None, limit: int = 20) -> list[dict]:
    resolved_run_id = run_id or latest_run_id()
    if not resolved_run_id:
        raise FileNotFoundError("No local runs found. Collect evidence first.")
    run = load_run(resolved_run_id)
    items = [evidence_from_dict(item) for item in run.get("evidence", [])]
    if sources:
        allowed = {source.lower() for source in sources}
        items = [item for item in items if item.source.lower() in allowed]
    scored = [(score_text(query, item), item) for item in items]
    return [item.to_dict() for score, item in sorted(scored, key=lambda pair: pair[0], reverse=True) if score > 0][:limit]


def coverage_warnings(run: dict[str, Any], runs_dir: Path = Path("runs")) -> list[str]:
    baseline = latest_complete_baseline(run, runs_dir)
    if not baseline:
        return []
    run_counts = evidence_counts(run)
    baseline_counts = evidence_counts(baseline)
    warnings = []
    for label, current, previous in (
        ("total evidence", run_counts["total"], baseline_counts["total"]),
        ("Webex messages", run_counts["webex_message"], baseline_counts["webex_message"]),
        ("Aha ideas", run_counts["aha_idea"], baseline_counts["aha_idea"]),
    ):
        if previous >= 20 and current < previous * 0.7:
            warnings.append(
                f"Coverage warning: {label} is {current}, below 70% of baseline {previous} from run {baseline.get('run_id')}."
            )
    return warnings


def latest_complete_baseline(run: dict[str, Any], runs_dir: Path) -> dict[str, Any] | None:
    if not runs_dir.exists():
        return None
    current_id = run.get("run_id")
    candidates = []
    for path in runs_dir.iterdir():
        if not path.is_dir() or path.name == current_id or not (path / "evidence.json").exists():
            continue
        try:
            candidate = load_run(path.name, runs_dir)
        except (OSError, ValueError):
            continue
        if candidate.get("feature_name") != run.get("feature_name"):
            continue
        sources = {str(source).lower() for source in candidate.get("sources") or []}
        if {"webex", "aha"}.issubset(sources) and evidence_counts(candidate)["total"] > 0:
            candidates.append(candidate)
    if not candidates:
        return None
    return max(candidates, key=lambda candidate: (evidence_counts(candidate)["total"], str(candidate.get("created_at") or "")))


def evidence_counts(run: dict[str, Any]) -> Counter:
    counts = Counter()
    for item in run.get("evidence") or []:
        source = str(item.get("source") or "")
        source_type = str(item.get("source_type") or "")
        counts["total"] += 1
        if source == "webex" and source_type == "webex_message":
            counts["webex_message"] += 1
        if source == "aha" and source_type == "aha_idea":
            counts["aha_idea"] += 1
        if source == "aha" and source_type == "aha_idea_comment":
            counts["aha_idea_comment"] += 1
    return counts
