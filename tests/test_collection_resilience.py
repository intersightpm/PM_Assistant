import pytest
import requests
import json

from pm_assistant.connectors.aha import AhaConnector
from pm_assistant.connectors.base import ConnectorResult
from pm_assistant.connectors.webex import WebexConnector
from pm_assistant.connectors.webex import request_with_retries
from pm_assistant.connectors.webex import webex_source_context
from pm_assistant.core.models import Evidence, FeatureConfig
from pm_assistant.core import workflows


class FakeConnector:
    def __init__(self, source, fail=False):
        self.source = source
        self.fail = fail

    def collect(self, config, date_range=None):
        if self.fail:
            raise RuntimeError("boom")
        return ConnectorResult(evidence=[
            Evidence(
                id=f"{self.source}-1",
                source=self.source,
                source_type=f"{self.source}_item",
                title="Webhook ask",
                text="Customer needs webhook support",
                requester="Example Customer",
            )
        ])


def test_collect_evidence_saves_source_checkpoints_and_partial_failures(monkeypatch):
    saved_runs = []
    checkpoints = []

    monkeypatch.setattr(workflows, "load_environment", lambda: None)
    monkeypatch.setattr(workflows, "load_feature_config", lambda feature, config_path=None: FeatureConfig(feature_name=feature, aliases=["webhook"]))
    monkeypatch.setattr(workflows, "make_run_id", lambda feature: "webhooks-test-run")
    monkeypatch.setattr(workflows, "save_run", lambda run: saved_runs.append(run) or "evidence.json")
    monkeypatch.setattr(workflows, "save_source_checkpoint", lambda run_id, source, data: checkpoints.append((run_id, source, data)) or f"{source}.json")
    monkeypatch.setattr(workflows, "get_connector", lambda source: FakeConnector(source, fail=source == "aha"))

    run = workflows.collect_evidence("webhooks", ["webex", "aha"])

    assert run.run_id == "webhooks-test-run"
    assert [checkpoint[1] for checkpoint in checkpoints] == ["webex", "aha"]
    assert any("aha: collection failed: boom" in warning for warning in run.warnings)
    assert len(saved_runs) >= 2
    assert run.evidence[0].source == "webex"
    assert run.metadata["status"] == "completed"
    assert checkpoints[0][2]["metadata"] == {}
    assert checkpoints[1][2]["metadata"]["status"] == "failed"


def test_aha_comments_are_collected_as_supporting_evidence_by_default(monkeypatch):
    class FakeAhaConnector(AhaConnector):
        def configured(self):
            return True, "ok"

        def request_json(self, path, params=None):
            if path == "/ideas":
                return {
                    "ideas": [{
                        "reference_num": "INI-I-1",
                        "name": "Webhook payload",
                        "description": "Customer needs webhook payload fields",
                        "created_at": "2026-01-01T00:00:00Z",
                    }],
                    "pagination": {"total_pages": 1},
                }
            if path.endswith("/comments"):
                return {
                    "comments": [{
                        "id": "comment-1",
                        "body": "Supporting webhook payload comment",
                        "created_at": "2026-01-02T00:00:00Z",
                    }]
                }
            return {"idea_endorsements": []}

    connector = FakeAhaConnector()
    result = connector.collect(FeatureConfig(feature_name="webhooks", aliases=["webhook"]))

    assert len(result.evidence) == 2
    assert result.evidence[0].source_type == "aha_idea"
    assert result.evidence[1].source_type == "aha_idea_comment"
    assert result.metadata["comments_enabled"] is True


def test_aha_customer_record_resolution_is_cached():
    class FakeAhaConnector(AhaConnector):
        def __init__(self):
            super().__init__()
            self.calls = 0

        def request_json(self, path, params=None):
            self.calls += 1
            assert path == "/custom_object_records/record-1"
            return {
                "custom_object_record": {
                    "custom_fields": [{"key": "customer_name", "name": "CAV Customer Name", "value": "ACME"}]
                }
            }

    connector = FakeAhaConnector()
    idea = {"custom_object_links": [{"key": "customers_list", "name": "Idea Customers", "record_ids": ["record-1"]}]}

    assert connector.collect_linked_idea_customers(idea, []) == ["ACME"]
    assert connector.collect_linked_idea_customers(idea, []) == ["ACME"]
    assert connector.calls == 1


def test_aha_collect_uses_full_idea_for_customer_and_opportunity_value():
    class FakeAhaConnector(AhaConnector):
        def __init__(self):
            super().__init__()
            self.paths = []

        def configured(self):
            return True, "ok"

        def request_json(self, path, params=None):
            self.paths.append(path)
            if path == "/ideas":
                return {
                    "ideas": [{
                        "reference_num": "INI-I-677",
                        "name": "Webhook custom headers",
                        "description": "Customer needs webhook custom headers",
                        "created_at": "2025-05-12T12:40:11.774Z",
                    }],
                    "pagination": {"total_pages": 1},
                }
            if path == "/ideas/INI-I-677":
                return {
                    "idea": {
                        "reference_num": "INI-I-677",
                        "custom_object_links": [{
                            "key": "customers_list",
                            "name": "Idea Customers",
                            "record_ids": ["record-1"],
                        }],
                        "custom_fields": [
                            {"key": "opportunity_value", "name": "Opportunity Value", "value": "$1M"}
                        ],
                    }
                }
            if path == "/custom_object_records/record-1":
                return {
                    "custom_object_record": {
                        "custom_fields": [
                            {"key": "customer_name", "name": "CAV Customer Name", "value": "GROUPE MUTUEL"}
                        ]
                    }
                }
            raise AssertionError(path)

    connector = FakeAhaConnector()
    result = connector.collect(FeatureConfig(
        feature_name="webhooks",
        aliases=["webhook"],
        source_filters={"aha_collect_comments": False},
    ))

    assert connector.paths.count("/ideas/INI-I-677") == 1
    assert len(result.evidence) == 1
    item = result.evidence[0]
    assert item.requester == "GROUPE MUTUEL"
    assert item.source_metadata["idea_customers"] == ["GROUPE MUTUEL"]
    assert item.source_metadata["opportunity_value"] == "$1M"
    assert item.source_metadata["opportunity_value_numeric"] == 1000000


def test_webex_request_retries_transient_status(monkeypatch):
    responses = []

    transient = requests.Response()
    transient.status_code = 502
    ok = requests.Response()
    ok.status_code = 200
    responses.extend([transient, ok])

    monkeypatch.setattr("pm_assistant.connectors.webex.time.sleep", lambda seconds: None)
    monkeypatch.setattr("pm_assistant.connectors.webex.requests.request", lambda *args, **kwargs: responses.pop(0))

    assert request_with_retries("get", "https://example.test").status_code == 200


def test_webex_request_does_not_retry_404(monkeypatch):
    calls = 0
    not_found = requests.Response()
    not_found.status_code = 404

    def fake_request(*args, **kwargs):
        nonlocal calls
        calls += 1
        return not_found

    monkeypatch.setattr("pm_assistant.connectors.webex.requests.request", fake_request)

    assert request_with_retries("get", "https://example.test").status_code == 404
    assert calls == 1


def test_webex_accuracy_collection_does_not_apply_fast_room_limit():
    class FakeWebexConnector(WebexConnector):
        def configured(self):
            return True, "ok"

        def get_access_token(self):
            return "token"

        def get_rooms(self, token):
            return [
                {"id": "1", "title": "Ask Intersight"},
                {"id": "2", "title": "Other Room"},
            ]

        def get_matching_messages(self, token, room, config, date_range=None):
            return [
                Evidence(
                    id=f"webex-{room['id']}",
                    source="webex",
                    source_type="webex_message",
                    title=room["title"],
                    text="Customer needs webhook support",
                )
            ]

    result = FakeWebexConnector().collect(FeatureConfig(
        feature_name="webhooks",
        aliases=["webhook"],
        source_filters={
            "collection_profile": "accuracy",
            "webex_room_contains": ["Ask Intersight"],
            "webex_max_rooms": 1,
        },
    ))

    assert len(result.evidence) == 2
    assert result.metadata["collection_profile"] == "accuracy"
    assert result.metadata["rooms_selected"] == 2


def test_webex_source_context_preserves_nearby_messages():
    messages = [
        {"id": "m1", "created": "2026-01-01T00:00:00Z", "personEmail": "pm@example.com", "text": "Is this available?", "parentId": "thread-1"},
        {"id": "m2", "created": "2026-01-01T00:01:00Z", "personEmail": "eng@example.com", "text": "It is already shipped and available.", "parentId": "thread-1"},
        {"id": "m3", "created": "2026-01-01T00:02:00Z", "personEmail": "other@example.com", "text": "Nearby room chatter"},
    ]

    context = webex_source_context(messages, 0)

    assert context[0]["position"] == "match"
    assert context[0]["message_id"] == "m1"
    assert context[1]["position"] == "nearby_thread"
    assert "already shipped" in context[1]["text"]
    assert context[2]["position"] == "nearby_room"


def test_coverage_guard_flags_unexpectedly_small_runs(tmp_path):
    baseline_dir = tmp_path / "baseline"
    current_dir = tmp_path / "current"
    baseline_dir.mkdir()
    current_dir.mkdir()
    baseline = {
        "run_id": "baseline",
        "feature_name": "webhooks",
        "sources": ["webex", "aha"],
        "warnings": [],
        "evidence": [
            *[
                {"source": "webex", "source_type": "webex_message"}
                for _ in range(100)
            ],
            *[
                {"source": "aha", "source_type": "aha_idea"}
                for _ in range(50)
            ],
        ],
    }
    current = {
        "run_id": "current",
        "feature_name": "webhooks",
        "sources": ["webex", "aha"],
        "warnings": [],
        "evidence": [
            *[
                {"source": "webex", "source_type": "webex_message"}
                for _ in range(20)
            ],
            *[
                {"source": "aha", "source_type": "aha_idea"}
                for _ in range(5)
            ],
        ],
    }
    (baseline_dir / "evidence.json").write_text(json.dumps(baseline), encoding="utf-8")
    (current_dir / "evidence.json").write_text(json.dumps(current), encoding="utf-8")

    warnings = workflows.coverage_warnings(current, tmp_path)

    assert any("total evidence" in warning for warning in warnings)
    assert any("Webex messages" in warning for warning in warnings)
    assert any("Aha ideas" in warning for warning in warnings)


def test_coverage_guard_uses_strongest_prior_baseline(tmp_path):
    weak_dir = tmp_path / "weak"
    strong_dir = tmp_path / "strong"
    current_dir = tmp_path / "current"
    for path in (weak_dir, strong_dir, current_dir):
        path.mkdir()
    weak = {
        "run_id": "weak",
        "feature_name": "webhooks",
        "sources": ["webex", "aha"],
        "evidence": [{"source": "webex", "source_type": "webex_message"} for _ in range(5)],
    }
    strong = {
        "run_id": "strong",
        "feature_name": "webhooks",
        "sources": ["webex", "aha"],
        "evidence": [{"source": "aha", "source_type": "aha_idea"} for _ in range(100)],
    }
    current = {
        "run_id": "current",
        "feature_name": "webhooks",
        "sources": ["webex", "aha"],
        "evidence": [{"source": "aha", "source_type": "aha_idea"} for _ in range(10)],
    }
    (weak_dir / "evidence.json").write_text(json.dumps(weak), encoding="utf-8")
    (strong_dir / "evidence.json").write_text(json.dumps(strong), encoding="utf-8")
    (current_dir / "evidence.json").write_text(json.dumps(current), encoding="utf-8")

    warnings = workflows.coverage_warnings(current, tmp_path)

    assert any("baseline 100 from run strong" in warning for warning in warnings)
