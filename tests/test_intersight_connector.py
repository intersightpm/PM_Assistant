import json

from pm_assistant.connectors import intersight


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_intersight_query_fans_out_all_accounts(monkeypatch):
    calls = []

    def fake_get(path, account=None, timeout=30):
        calls.append((account, path))
        return FakeResponse({"Results": [{"Moid": f"{account}-1", "Name": f"{account} device"}]})

    monkeypatch.setattr("pm_assistant.auth.intersight_auth.get", fake_get)

    result = intersight.query("all", "compute/PhysicalSummaries", top=10)

    assert result["merged_count"] == 2
    assert {call[0] for call in calls} == {"us", "eu"}
    assert all("%24top=10" in call[1] for call in calls)


def test_intersight_filter_expression_and_count(monkeypatch):
    paths = []

    def fake_get(path, account=None, timeout=30):
        paths.append(path)
        return FakeResponse({"Results": [{"Moid": "1"}, {"Moid": "2"}]})

    monkeypatch.setattr("pm_assistant.auth.intersight_auth.get", fake_get)

    result = intersight.count("us", "cond/Alarms", filters={"Severity": "Critical"})

    assert result["merged_count"] == 2
    assert "%24filter=Severity+eq+%27Critical%27" in paths[0]


def test_normalize_record_shape():
    record = intersight.normalize_record(
        {
            "Moid": "moid-1",
            "Name": "Server 1",
            "Serial": "ABC",
            "Model": "UCS",
            "OperState": "OK",
            "Health": "Healthy",
            "Organization": {"Name": "Org A"},
        },
        "us",
        "compute/PhysicalSummaries",
    )

    assert record["account"] == "us"
    assert record["moid"] == "moid-1"
    assert record["organization"] == "Org A"
    assert record["raw"]["Serial"] == "ABC"


def test_inventory_summary_handles_partial_failure(monkeypatch):
    def fake_query(account, object_type, filters=None, top=100):
        return {
            "accounts": {
                "us": {"ok": True, "records": [{"Moid": "1", "Name": "US"}]},
                "eu": {"ok": False, "records": [], "error": "boom"},
            },
            "merged_count": 1,
        }

    monkeypatch.setattr(intersight, "query", fake_query)

    result = intersight.inventory_summary("all")

    assert result["merged_counts"]["compute/PhysicalSummaries"] == 1
    assert any("boom" in warning for warning in result["warnings"])


def test_inventory_summary_save(tmp_path, monkeypatch):
    monkeypatch.setattr(
        intersight,
        "query",
        lambda account, object_type, filters=None, top=100: {"accounts": {"us": {"ok": True, "records": []}}, "merged_count": 0},
    )

    result = intersight.inventory_summary("us", save=True, runs_dir=tmp_path)

    assert result["run_id"].startswith("intersight_inventory-")
    assert (tmp_path / result["run_id"] / "intersight_inventory.json").exists()


def test_adoption_signals_uses_inventory_and_health(monkeypatch):
    monkeypatch.setattr(intersight, "inventory_summary", lambda account, save=False: {"merged_counts": {"compute/PhysicalSummaries": 3}, "warnings": []})
    monkeypatch.setattr(intersight, "health_summary", lambda account, save=False: {"merged_counts": {"cond/Alarms": 1}, "warnings": []})

    result = intersight.adoption_signals("server management", account="all")

    assert result["source"] == "intersight"
    assert result["signals"]["managed_assets"]["compute/PhysicalSummaries"] == 3
    assert result["signals"]["health_friction"]["cond/Alarms"] == 1
