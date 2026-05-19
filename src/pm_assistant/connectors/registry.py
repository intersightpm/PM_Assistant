from __future__ import annotations

from .aha import AhaConnector
from .base import Connector
from .jira import JiraConnector
from .snowflake import SnowflakeConnector
from .webex import WebexConnector

SUPPORTED_SOURCES = ("aha", "webex", "jira", "snowflake")


def get_connector(name: str) -> Connector:
    normalized = name.strip().lower()
    if normalized == "aha":
        return AhaConnector()
    if normalized == "webex":
        return WebexConnector()
    if normalized == "jira":
        return JiraConnector()
    if normalized == "snowflake":
        return SnowflakeConnector()
    raise ValueError(f"Unknown source '{name}'. Supported sources: {', '.join(SUPPORTED_SOURCES)}")


def parse_sources(value: str | list[str]) -> list[str]:
    if isinstance(value, str):
        sources = [item.strip().lower() for item in value.split(",")]
    else:
        sources = [str(item).strip().lower() for item in value]
    return [source for source in sources if source]
