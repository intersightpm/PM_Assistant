from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .report_workflow import build_report_input, report_format_path
from .storage import RUNS_DIR, load_run


def prepare_prd_input(
    topic: str,
    run_id: str,
    research_run_id: str | None = None,
    runs_dir: Path = RUNS_DIR,
) -> dict[str, Any]:
    run = load_run(run_id, runs_dir=runs_dir)
    package = {
        "schema_version": 1,
        "artifact_type": "prd",
        "topic": topic,
        "run_id": run_id,
        "format_name": "prd",
        "format_path": str(report_format_path("prd")),
        "feedback": build_report_input(topic, run),
        "research": load_research_packet(research_run_id, runs_dir=runs_dir) if research_run_id else None,
        "instructions": [
            "Codex writes the PRD from evidence and optional research.",
            "Do not invent customers, dates, adoption numbers, or citations.",
            "Call validate_prd after writing runs/<run-id>/prd.md.",
        ],
    }
    output_path = runs_dir / run_id / "prd_input.json"
    output_path.write_text(json.dumps(package, indent=2), encoding="utf-8", newline="\n")
    return package


def validate_prd(run_id: str, markdown_path: Path | None = None, runs_dir: Path = RUNS_DIR) -> dict[str, Any]:
    path = markdown_path or runs_dir / run_id / "prd.md"
    markdown = path.read_text(encoding="utf-8")
    errors: list[str] = []
    required_sections = [
        "# ",
        "## Problem",
        "## Evidence",
        "## Goals",
        "## Non-goals",
        "## Requirements",
        "## Success Metrics",
        "## Open Questions",
    ]
    for section in required_sections:
        if section not in markdown:
            errors.append(f"Missing PRD section: {section.strip()}")
    if "http" not in markdown and "webexteams://" not in markdown:
        errors.append("PRD should cite at least one internal evidence link or external research URL.")
    return {"ok": not errors, "errors": errors}


def save_research_packet(
    topic: str,
    findings: list[dict[str, Any]] | dict[str, Any],
    citations: list[dict[str, Any]] | None = None,
    run_id: str | None = None,
    runs_dir: Path = RUNS_DIR,
) -> dict[str, Any]:
    resolved_run_id = run_id or make_artifact_run_id(topic, "research")
    packet = {
        "schema_version": 1,
        "artifact_type": "research",
        "topic": topic,
        "run_id": resolved_run_id,
        "created_at": utc_now_iso(),
        "findings": findings if isinstance(findings, list) else [findings],
        "citations": citations or [],
        "instructions": [
            "Use citations only for facts they directly support.",
            "Keep external research separate from internal customer evidence.",
        ],
    }
    run_dir = runs_dir / resolved_run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "research.json"
    path.write_text(json.dumps(packet, indent=2), encoding="utf-8", newline="\n")
    return {"run_id": resolved_run_id, "research_path": str(path), "packet": packet}


def load_research_packet(run_id: str, runs_dir: Path = RUNS_DIR) -> dict[str, Any]:
    path = runs_dir / run_id / "research.json"
    if not path.exists():
        raise FileNotFoundError(f"Research packet for run '{run_id}' was not found at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def prepare_jira_update_input(
    issue: dict[str, Any],
    run_id: str | None = None,
    artifact_path: str | None = None,
    runs_dir: Path = RUNS_DIR,
) -> dict[str, Any]:
    evidence = load_run(run_id, runs_dir=runs_dir) if run_id else None
    package = {
        "schema_version": 1,
        "artifact_type": "jira_update",
        "issue": issue,
        "run_id": run_id,
        "evidence": evidence,
        "artifact_path": artifact_path,
        "format_name": "jira_update",
        "format_path": str(report_format_path("jira_update")),
        "instructions": [
            "Codex writes a concise Jira comment/update draft.",
            "Do not call jira_add_comment until the user explicitly asks to post it.",
            "Mention evidence links and open questions when relevant.",
        ],
    }
    output_run_id = run_id or make_artifact_run_id(str(issue.get("key") or "jira"), "jira-update")
    run_dir = runs_dir / output_run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "jira_update_input.json"
    path.write_text(json.dumps(package, indent=2), encoding="utf-8", newline="\n")
    package["input_path"] = str(path)
    return package


def prepare_snowflake_adoption_summary_input(
    topic: str,
    query_result: dict[str, Any],
    query_name: str | None = None,
    run_id: str | None = None,
    runs_dir: Path = RUNS_DIR,
) -> dict[str, Any]:
    resolved_run_id = run_id or make_artifact_run_id(topic, "adoption")
    package = {
        "schema_version": 1,
        "artifact_type": "adoption_summary",
        "topic": topic,
        "run_id": resolved_run_id,
        "format_name": "adoption_summary",
        "format_path": str(report_format_path("adoption_summary")),
        "query_name": query_name,
        "query_result": query_result,
        "created_at": utc_now_iso(),
        "instructions": [
            "Codex writes the adoption summary from the provided Snowflake result.",
            "State the source query/template and row count.",
            "Use Not available for missing metrics or segments.",
        ],
    }
    run_dir = runs_dir / resolved_run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "adoption_input.json"
    path.write_text(json.dumps(package, indent=2), encoding="utf-8", newline="\n")
    package["input_path"] = str(path)
    return package


def prepare_adoption_summary_input(
    topic: str,
    source_signals: dict[str, Any],
    run_id: str | None = None,
    runs_dir: Path = RUNS_DIR,
) -> dict[str, Any]:
    resolved_run_id = run_id or source_signals.get("run_id") or make_artifact_run_id(topic, "adoption")
    package = {
        "schema_version": 2,
        "artifact_type": "adoption_summary",
        "topic": topic,
        "run_id": resolved_run_id,
        "format_name": "adoption_summary",
        "format_path": str(report_format_path("adoption_summary")),
        "created_at": utc_now_iso(),
        "sources": source_signals.get("sources", []),
        "source_signals": source_signals.get("source_signals", {}),
        "metric_candidates": source_signals.get("metric_candidates", {}),
        "warnings": source_signals.get("warnings", []),
        "known_gaps": source_signals.get("known_gaps", []),
        "instructions": [
            "Codex writes the adoption summary from the provided source signals.",
            "State which sources contributed data and which metrics are not available.",
            "Do not infer adoption from one source if the metric requires another source.",
        ],
    }
    run_dir = runs_dir / resolved_run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "adoption_input.json"
    path.write_text(json.dumps(package, indent=2), encoding="utf-8", newline="\n")
    package["input_path"] = str(path)
    return package


def make_artifact_run_id(topic: str, suffix: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-") or "topic"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{slug}-{suffix}-{stamp}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
