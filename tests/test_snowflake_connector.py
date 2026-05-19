from pathlib import Path

import pytest

from pm_assistant.connectors.registry import get_connector
from pm_assistant.connectors.snowflake import (
    ReadOnlySqlError,
    SnowflakeConnector,
    list_query_templates,
    load_query_template,
    validate_read_only_sql,
)


@pytest.mark.parametrize(
    "sql",
    [
        "select * from MY_TABLE",
        "WITH rows AS (SELECT 1 AS id) SELECT * FROM rows",
        "SHOW TABLES",
        "DESCRIBE TABLE MY_TABLE",
        "EXPLAIN SELECT * FROM MY_TABLE",
    ],
)
def test_allows_read_only_sql(sql):
    assert validate_read_only_sql(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO T VALUES (1)",
        "UPDATE T SET A = 1",
        "DELETE FROM T",
        "DROP TABLE T",
        "USE ROLE ACCOUNTADMIN",
        "SELECT 1; SELECT 2",
    ],
)
def test_blocks_mutating_or_multi_statement_sql(sql):
    with pytest.raises(ReadOnlySqlError):
        validate_read_only_sql(sql)


def test_registry_returns_snowflake_connector():
    assert isinstance(get_connector("snowflake"), SnowflakeConnector)


def test_lists_and_loads_query_templates(tmp_path: Path):
    (tmp_path / "Adoption.sql").write_text("SELECT 1 AS ok;", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignore", encoding="utf-8")

    assert list_query_templates(tmp_path) == ["Adoption.sql"]
    assert load_query_template("Adoption", tmp_path) == "SELECT 1 AS ok"


def test_rejects_mutating_query_template(tmp_path: Path):
    (tmp_path / "Bad.sql").write_text("DROP TABLE T", encoding="utf-8")

    with pytest.raises(ReadOnlySqlError):
        load_query_template("Bad.sql", tmp_path)


def test_snowflake_doctor_uses_connection_summary(monkeypatch):
    monkeypatch.setattr(
        "pm_assistant.connectors.snowflake.connection_summary",
        lambda: {"user": "PM_USER", "role": "PM_ROLE", "warehouse": "PM_WH"},
    )

    result = SnowflakeConnector().doctor()

    assert result.warnings == ["Snowflake connection check passed for PM_USER using role PM_ROLE and warehouse PM_WH."]
