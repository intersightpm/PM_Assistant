from pm_assistant.core import adoption
from pm_assistant.core.pm_workflows import prepare_adoption_summary_input


def test_collect_adoption_signals_from_intersight_only(monkeypatch):
    monkeypatch.setattr(
        "pm_assistant.connectors.intersight.adoption_signals",
        lambda topic, account="all": {
            "source": "intersight",
            "topic": topic,
            "signals": {"managed_assets": {"compute/PhysicalSummaries": 2}},
            "warnings": [],
        },
    )

    result = adoption.collect_adoption_signals("server management", ["intersight"])

    assert result["sources"] == ["intersight"]
    assert result["metric_candidates"]["intersight_managed_assets"]["compute/PhysicalSummaries"] == 2


def test_collect_adoption_signals_from_snowflake_only(monkeypatch):
    monkeypatch.setattr("pm_assistant.core.adoption.default_snowflake_template", lambda: "Adoption.sql")
    monkeypatch.setattr(
        "pm_assistant.core.adoption.run_query_template",
        lambda template, max_rows=100: {"row_count": 5, "columns": ["FEATURE", "COUNT"], "rows": []},
    )

    result = adoption.collect_adoption_signals("webhooks", ["snowflake"])

    assert result["source_signals"]["snowflake"]["query_template"] == "Adoption.sql"
    assert result["metric_candidates"]["snowflake_rows"] == 5


def test_collect_adoption_signals_from_both_sources(monkeypatch):
    monkeypatch.setattr("pm_assistant.core.adoption.default_snowflake_template", lambda: "Adoption.sql")
    monkeypatch.setattr(
        "pm_assistant.core.adoption.run_query_template",
        lambda template, max_rows=100: {"row_count": 5, "columns": ["FEATURE"], "rows": []},
    )
    monkeypatch.setattr(
        "pm_assistant.connectors.intersight.adoption_signals",
        lambda topic, account="all": {
            "source": "intersight",
            "topic": topic,
            "signals": {"managed_assets": {"compute/PhysicalSummaries": 2}, "health_friction": {"cond/Alarms": 1}},
            "warnings": [],
        },
    )

    result = adoption.collect_adoption_signals("webhooks", ["snowflake", "intersight"])

    assert set(result["source_signals"]) == {"snowflake", "intersight"}
    assert result["metric_candidates"]["snowflake_rows"] == 5
    assert result["metric_candidates"]["intersight_health_friction"]["cond/Alarms"] == 1


def test_prepare_adoption_summary_input_persists_generic_artifact(tmp_path):
    signals = {
        "sources": ["snowflake", "intersight"],
        "source_signals": {"snowflake": {"row_count": 1}},
        "metric_candidates": {"snowflake_rows": 1},
        "warnings": [],
        "known_gaps": [],
    }

    package = prepare_adoption_summary_input("webhooks", signals, run_id="adoption-run", runs_dir=tmp_path)

    assert package["artifact_type"] == "adoption_summary"
    assert package["sources"] == ["snowflake", "intersight"]
    assert (tmp_path / "adoption-run" / "adoption_input.json").exists()
