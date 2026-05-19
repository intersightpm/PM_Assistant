from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from .models import FeatureConfig

DEFAULT_CONFIG_DIR = Path("configs")


def load_environment() -> None:
    load_dotenv(override=False)
    try:
        from pm_assistant.auth.codex_auth_common import load_env_file
    except ImportError:
        return
    for filename in ("aha.env", "webex.env", "jira.env", "snowflake.env", "intersight.env"):
        load_env_file(filename)


def load_feature_config(feature_name: str, config_path: str | None = None) -> FeatureConfig:
    path = Path(config_path) if config_path else DEFAULT_CONFIG_DIR / f"{slugify(feature_name)}.yaml"
    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    else:
        data = {"feature_name": feature_name}

    data.setdefault("feature_name", feature_name)
    return FeatureConfig(
        feature_name=str(data.get("feature_name") or feature_name),
        aliases=listify(data.get("aliases")),
        related_terms=listify(data.get("related_terms")),
        exclude_terms=listify(data.get("exclude_terms")),
        related_terms_match_without_feature=bool(data.get("related_terms_match_without_feature", False)),
        source_filters=dict(data.get("source_filters") or {}),
        category_hints=listify(data.get("category_hints")),
        report=dict(data.get("report") or {}),
    )


def listify(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)] if str(value).strip() else []


def slugify(value: str) -> str:
    return "-".join(value.lower().replace("_", "-").split())
