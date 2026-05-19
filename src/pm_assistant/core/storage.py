from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import Evidence, RunResult

RUNS_DIR = Path("runs")


def save_run(run: RunResult, runs_dir: Path = RUNS_DIR) -> Path:
    run_dir = runs_dir / run.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "evidence.json"
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(run.to_dict(), handle, indent=2)
    return path


def save_source_checkpoint(run_id: str, source: str, data: dict[str, Any], runs_dir: Path = RUNS_DIR) -> Path:
    checkpoint_dir = runs_dir / run_id / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    path = checkpoint_dir / f"{source}.json"
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, indent=2)
    return path


def load_run(run_id: str, runs_dir: Path = RUNS_DIR) -> dict:
    path = runs_dir / run_id / "evidence.json"
    if not path.exists():
        raise FileNotFoundError(f"Run '{run_id}' was not found at {path}")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def latest_run_id(runs_dir: Path = RUNS_DIR) -> str | None:
    if not runs_dir.exists():
        return None
    candidates = [path.name for path in runs_dir.iterdir() if (path / "evidence.json").exists()]
    return sorted(candidates)[-1] if candidates else None


def evidence_from_dict(data: dict) -> Evidence:
    return Evidence(
        id=str(data.get("id", "")),
        source=str(data.get("source", "")),
        source_type=str(data.get("source_type", "")),
        title=str(data.get("title", "")),
        text=str(data.get("text", "")),
        author=str(data.get("author", "")),
        requester=str(data.get("requester", "")),
        created_at=str(data.get("created_at", "")),
        updated_at=str(data.get("updated_at", "")),
        url=str(data.get("url", "")),
        raw_excerpt=str(data.get("raw_excerpt", "")),
        source_metadata=dict(data.get("source_metadata") or {}),
    )
