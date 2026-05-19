from __future__ import annotations

import base64

import pytest
import requests

from pm_assistant.connectors.jira import JiraConnector, adf_text, comment_doc, issue_to_evidence
from pm_assistant.connectors.registry import get_connector
from pm_assistant.core.models import FeatureConfig


def jira_issue(key: str = "ISSDK-1") -> dict:
    return {
        "key": key,
        "fields": {
            "summary": "Webhook payload support",
            "status": {"name": "In Progress"},
            "issuetype": {"name": "Story"},
            "priority": {"name": "P2"},
            "project": {"key": "ISSDK"},
            "assignee": {"displayName": "Engineer"},
            "reporter": {"displayName": "Reporter"},
            "created": "2026-01-01T00:00:00.000+0000",
            "updated": "2026-01-02T00:00:00.000+0000",
            "labels": ["webhook"],
            "components": [{"name": "API"}],
            "fixVersions": [{"name": "1.0"}],
            "description": {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Need webhook payload fields"}]}]},
            "comment": {
                "total": 1,
                "comments": [{
                    "id": "10000",
                    "author": {"displayName": "Commenter"},
                    "created": "2026-01-03T00:00:00.000+0000",
                    "body": {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Customer is blocked"}]}]},
                }],
            },
        },
    }


@pytest.fixture
def jira_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "user@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "token")
    monkeypatch.delenv("JIRA_OAUTH_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("JIRA_PAT", raising=False)


def test_registry_accepts_jira() -> None:
    assert isinstance(get_connector("jira"), JiraConnector)


def test_jira_headers_use_regular_api_token(jira_env) -> None:
    headers = JiraConnector().headers()
    expected = base64.b64encode(b"user@example.com:token").decode("ascii")

    assert headers["Authorization"] == f"Basic {expected}"


def test_jira_issue_to_evidence_normalizes_adf(jira_env) -> None:
    item = issue_to_evidence(jira_issue(), "https://example.atlassian.net")

    assert item.source == "jira"
    assert item.source_type == "jira_issue"
    assert item.url == "https://example.atlassian.net/browse/ISSDK-1"
    assert "Need webhook payload fields" in item.text
    assert "Customer is blocked" in item.text
    assert item.source_metadata["status"] == "In Progress"


def test_jira_collect_searches_and_filters(monkeypatch: pytest.MonkeyPatch, jira_env) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"issues": [jira_issue()]}

    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return FakeResponse()

    monkeypatch.setattr(requests, "request", fake_request)

    result = JiraConnector().collect(FeatureConfig(feature_name="webhooks", aliases=["webhook"]))

    assert len(result.evidence) == 1
    assert "text ~" in calls[0][2]["params"]["jql"]


def test_comment_doc_can_include_real_mention() -> None:
    doc = comment_doc("could you please provide an update?", mention_account_id="abc", mention_display_name="Swetha Manjunath")

    paragraph = doc["content"][0]["content"]
    assert paragraph[0]["type"] == "mention"
    assert paragraph[0]["attrs"]["id"] == "abc"
    assert adf_text(doc) == "@Swetha Manjunath could you please provide an update?"


def test_jira_add_comment_posts_adf(monkeypatch: pytest.MonkeyPatch, jira_env) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "id": "1757479",
                "created": "2026-05-14T19:25:06.608+0000",
                "author": {"displayName": "Karthik Shankar"},
                "body": comment_doc("status?", mention_account_id="abc", mention_display_name="Swetha Manjunath"),
            }

    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return FakeResponse()

    monkeypatch.setattr(requests, "request", fake_request)

    result = JiraConnector().add_comment("ISSDK-1717", "status?", mention_account_id="abc", mention_display_name="Swetha Manjunath")

    assert calls[0][0] == "POST"
    assert calls[0][1].endswith("/rest/api/3/issue/ISSDK-1717/comment")
    assert calls[0][2]["json"]["body"]["content"][0]["content"][0]["type"] == "mention"
    assert result["id"] == "1757479"
