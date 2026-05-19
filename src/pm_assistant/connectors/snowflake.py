from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import sqlparse
from sqlparse import tokens as T

from pm_assistant.auth import snowflake_auth
from pm_assistant.core.models import Evidence, FeatureConfig

from .base import Connector, ConnectorResult

QUERIES_DIR = Path("queries")
_ALLOWED_FIRST_KEYWORDS = {"SELECT", "WITH", "SHOW", "DESCRIBE", "DESC", "EXPLAIN"}
_BLOCKED_KEYWORDS = {
    "ALTER",
    "BEGIN",
    "CALL",
    "COMMIT",
    "COPY",
    "CREATE",
    "DELETE",
    "DROP",
    "GRANT",
    "INSERT",
    "MERGE",
    "PUT",
    "REMOVE",
    "REVOKE",
    "ROLLBACK",
    "TRUNCATE",
    "UPDATE",
    "USE",
}


class ReadOnlySqlError(ValueError):
    pass


class SnowflakeConnector(Connector):
    name = "snowflake"

    def doctor(self) -> ConnectorResult:
        try:
            summary = connection_summary()
        except Exception as exc:
            return ConnectorResult(warnings=[f"Snowflake connection check failed: {exc}"])
        user = summary.get("user") or "unknown user"
        role = summary.get("role") or "unknown role"
        warehouse = summary.get("warehouse") or "unknown warehouse"
        return ConnectorResult(warnings=[f"Snowflake connection check passed for {user} using role {role} and warehouse {warehouse}."])

    def collect(self, config: FeatureConfig, date_range: str | None = None) -> ConnectorResult:
        filters = config.source_filters or {}
        template = filters.get("snowflake_query_template")
        sql = filters.get("snowflake_sql")
        if template:
            result = run_query_template(str(template))
            title = f"Snowflake template: {template}"
        elif sql:
            result = run_query(str(sql))
            title = "Snowflake configured SQL"
        else:
            return ConnectorResult(
                warnings=["Snowflake collection skipped: configure source_filters.snowflake_query_template or source_filters.snowflake_sql."],
                metadata={"available_templates": list_query_templates()},
            )
        text = json.dumps(result, indent=2)
        return ConnectorResult(
            evidence=[
                Evidence(
                    id=f"snowflake-{config.feature_name}",
                    source="snowflake",
                    source_type="snowflake_query_result",
                    title=title,
                    text=text,
                    requester="PM Assistant",
                    raw_excerpt=text[:800],
                    source_metadata={"date_range": date_range, "columns": result.get("columns"), "row_count": result.get("row_count")},
                )
            ],
            metadata={"query": result.get("query"), "row_count": result.get("row_count"), "columns": result.get("columns")},
        )


def validate_read_only_sql(sql: str) -> str:
    cleaned = sql.strip()
    if not cleaned:
        raise ReadOnlySqlError("Enter a SQL statement.")

    statements = [statement for statement in sqlparse.parse(cleaned) if str(statement).strip()]
    if len(statements) != 1:
        raise ReadOnlySqlError("Only one SQL statement is allowed.")

    first_keyword = _first_keyword(statements[0])
    if first_keyword not in _ALLOWED_FIRST_KEYWORDS:
        raise ReadOnlySqlError(f"Only read-only SQL is allowed. Found: {first_keyword or 'unknown'}.")

    for token in statements[0].flatten():
        if token.ttype in T.Keyword and token.normalized.upper() in _BLOCKED_KEYWORDS:
            raise ReadOnlySqlError(f"Blocked SQL keyword: {token.normalized.upper()}.")

    return cleaned.rstrip(";")


def run_query(sql: str, max_rows: int = 100) -> dict[str, Any]:
    safe_sql = validate_read_only_sql(sql)
    pandas = _pandas()
    with snowflake_auth.connect() as conn:
        frame = pandas.read_sql(safe_sql, conn)
    return dataframe_result(frame, safe_sql, max_rows=max_rows)


def connection_summary() -> dict[str, Any]:
    return snowflake_auth.test_connection()


def list_query_templates(queries_dir: Path = QUERIES_DIR) -> list[str]:
    if not queries_dir.exists():
        return []
    return sorted(path.name for path in queries_dir.glob("*.sql") if path.is_file())


def load_query_template(name: str, queries_dir: Path = QUERIES_DIR) -> str:
    safe_name = Path(name).name
    if not safe_name.lower().endswith(".sql"):
        safe_name += ".sql"
    path = queries_dir / safe_name
    if not path.exists():
        raise FileNotFoundError(f"Snowflake query template '{name}' was not found at {path}")
    return validate_read_only_sql(path.read_text(encoding="utf-8"))


def run_query_template(name: str, max_rows: int = 100) -> dict[str, Any]:
    return run_query(load_query_template(name), max_rows=max_rows)


def dataframe_result(frame: Any, query: str, max_rows: int = 100) -> dict[str, Any]:
    preview = frame.head(max(1, int(max_rows)))
    rows = json.loads(preview.to_json(orient="records", date_format="iso"))
    return {
        "query": query,
        "columns": [str(column) for column in frame.columns],
        "row_count": int(len(frame.index)),
        "preview_row_count": len(rows),
        "rows": rows,
        "truncated": len(frame.index) > len(rows),
    }


def _first_keyword(statement: sqlparse.sql.Statement) -> str | None:
    for token in statement.flatten():
        if token.is_whitespace or token.ttype in T.Comment:
            continue
        return token.normalized.upper()
    return None


def _pandas() -> Any:
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("Missing optional dependency 'pandas'. Install with: python -m pip install pandas") from exc
    return pd
