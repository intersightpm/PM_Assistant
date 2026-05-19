from __future__ import annotations

import base64
import os
from typing import Any

import requests

from pm_assistant.core.matching import text_matches_feature
from pm_assistant.core.models import Evidence, FeatureConfig

from .base import Connector, ConnectorResult


class JiraConfigError(RuntimeError):
    pass


class JiraConnector(Connector):
    name = "jira"

    def __init__(self) -> None:
        self.base = (os.getenv("JIRA_BASE_URL") or "").rstrip("/")
        self.email = os.getenv("JIRA_EMAIL") or ""
        self.api_token = os.getenv("JIRA_API_TOKEN") or ""
        self.oauth_token = os.getenv("JIRA_OAUTH_ACCESS_TOKEN") or ""
        self.pat = os.getenv("JIRA_PAT") or ""

    def configured(self) -> tuple[bool, str]:
        if not self.base:
            return False, "JIRA_BASE_URL is missing. Set it to your Jira site, for example https://company.atlassian.net."
        if self.oauth_token or self.pat:
            return True, "Jira bearer token credentials are present."
        if self.email and self.api_token:
            return True, "Jira email/API token credentials are present."
        return False, "Jira auth is missing. Set JIRA_EMAIL and JIRA_API_TOKEN, or set JIRA_OAUTH_ACCESS_TOKEN/JIRA_PAT."

    def headers(self) -> dict[str, str]:
        ok, message = self.configured()
        if not ok:
            raise JiraConfigError(message)
        if self.oauth_token:
            authorization = f"Bearer {self.oauth_token}"
        elif self.pat:
            authorization = f"Bearer {self.pat}"
        else:
            raw = f"{self.email}:{self.api_token}".encode("utf-8")
            authorization = f"Basic {base64.b64encode(raw).decode('ascii')}"
        return {"Authorization": authorization, "Accept": "application/json", "Content-Type": "application/json"}

    def request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        url = f"{self.base}{path}"
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.update(self.headers())
        response = requests.request(method, url, headers=headers, timeout=kwargs.pop("timeout", 30), **kwargs)
        response.raise_for_status()
        return response

    def doctor(self) -> ConnectorResult:
        ok, message = self.configured()
        if not ok:
            return ConnectorResult(warnings=[message])
        try:
            response = self.request("GET", "/rest/api/3/myself")
            user = response.json().get("displayName") or response.json().get("emailAddress") or "unknown user"
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            return ConnectorResult(warnings=[f"Jira API check failed with HTTP {status}. Verify Jira credentials and permissions."])
        except requests.RequestException as exc:
            return ConnectorResult(warnings=[f"Jira API check failed: {exc}"])
        return ConnectorResult(warnings=[f"Jira API check passed for {user}."])

    def collect(self, config: FeatureConfig, date_range: str | None = None) -> ConnectorResult:
        ok, message = self.configured()
        if not ok:
            return ConnectorResult(warnings=[message])
        max_results = int(config.source_filters.get("jira_max_results") or 50)
        comments_limit = int(config.source_filters.get("jira_comments_limit") or 5)
        jql = build_feature_jql(config, date_range=date_range)
        try:
            issues = self.search_issues(jql, max_results=max_results)
        except requests.RequestException as exc:
            return ConnectorResult(warnings=[f"Jira collection failed: {exc}"])

        evidence: list[Evidence] = []
        for issue in issues:
            item = issue_to_evidence(issue, self.base, comments_limit=comments_limit)
            if text_matches_feature(f"{item.title}\n{item.text}", config):
                evidence.append(item)
        return ConnectorResult(evidence=evidence, metadata={"jql": jql, "issues_scanned": len(issues), "max_results": max_results})

    def search_issues(self, jql: str, max_results: int = 20) -> list[dict[str, Any]]:
        fields = [
            "summary",
            "status",
            "assignee",
            "reporter",
            "created",
            "updated",
            "priority",
            "issuetype",
            "project",
            "description",
            "comment",
            "labels",
            "components",
            "fixVersions",
        ]
        response = self.request(
            "GET",
            "/rest/api/3/search/jql",
            params={"jql": jql, "maxResults": max(1, min(max_results, 100)), "fields": ",".join(fields)},
        )
        return list(response.json().get("issues") or [])

    def read_issue(self, issue_key: str) -> dict[str, Any]:
        fields = (
            "summary,status,assignee,reporter,created,updated,priority,issuetype,project,"
            "description,comment,labels,components,fixVersions"
        )
        response = self.request("GET", f"/rest/api/3/issue/{issue_key}", params={"fields": fields})
        return normalize_issue(response.json(), self.base)

    def add_comment(
        self,
        issue_key: str,
        comment: str,
        mention_account_id: str | None = None,
        mention_display_name: str | None = None,
    ) -> dict[str, Any]:
        response = self.request(
            "POST",
            f"/rest/api/3/issue/{issue_key}/comment",
            json={"body": comment_doc(comment, mention_account_id=mention_account_id, mention_display_name=mention_display_name)},
        )
        data = response.json()
        return {
            "id": data.get("id"),
            "created": data.get("created"),
            "author": (data.get("author") or {}).get("displayName"),
            "body": adf_text(data.get("body")),
        }


def build_feature_jql(config: FeatureConfig, date_range: str | None = None) -> str:
    terms = config.all_positive_terms()[:8] or [config.feature_name]
    text_query = " OR ".join(f'text ~ "{escape_jql(term)}"' for term in terms)
    clauses = [f"({text_query})"]
    if date_range:
        start = date_range.split("..", 1)[0].split(",", 1)[0].strip()
        if start:
            clauses.append(f'updated >= "{escape_jql(start)}"')
    return " AND ".join(clauses) + " ORDER BY updated DESC"


def escape_jql(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def issue_to_evidence(issue: dict[str, Any], base_url: str, comments_limit: int = 5) -> Evidence:
    normalized = normalize_issue(issue, base_url, comments_limit=comments_limit)
    text_parts = [
        normalized.get("description") or "",
        *(comment.get("body") or "" for comment in normalized.get("comments") or []),
    ]
    return Evidence(
        id=f"jira-{normalized['key']}",
        source="jira",
        source_type="jira_issue",
        title=str(normalized.get("summary") or normalized["key"]),
        text="\n\n".join(part for part in text_parts if part),
        author=str(normalized.get("reporter") or ""),
        requester=str(normalized.get("reporter") or ""),
        created_at=str(normalized.get("created") or ""),
        updated_at=str(normalized.get("updated") or ""),
        url=str(normalized.get("url") or ""),
        source_metadata={
            key: value
            for key, value in normalized.items()
            if key not in {"description", "comments", "url", "summary", "created", "updated"}
        },
    )


def normalize_issue(issue: dict[str, Any], base_url: str, comments_limit: int = 5) -> dict[str, Any]:
    fields = issue.get("fields") or {}
    comments = (fields.get("comment") or {}).get("comments") or []
    recent_comments = comments[-comments_limit:] if comments_limit >= 0 else comments
    key = issue.get("key") or ""
    return {
        "key": key,
        "url": f"{base_url}/browse/{key}" if key else "",
        "summary": fields.get("summary"),
        "status": (fields.get("status") or {}).get("name"),
        "issue_type": (fields.get("issuetype") or {}).get("name"),
        "priority": (fields.get("priority") or {}).get("name"),
        "project": (fields.get("project") or {}).get("key"),
        "assignee": (fields.get("assignee") or {}).get("displayName"),
        "reporter": (fields.get("reporter") or {}).get("displayName"),
        "created": fields.get("created"),
        "updated": fields.get("updated"),
        "labels": fields.get("labels") or [],
        "components": [component.get("name") for component in fields.get("components") or []],
        "fixVersions": [version.get("name") for version in fields.get("fixVersions") or []],
        "description": adf_text(fields.get("description")),
        "comments": [
            {
                "id": comment.get("id"),
                "author": (comment.get("author") or {}).get("displayName"),
                "created": comment.get("created"),
                "body": adf_text(comment.get("body")),
            }
            for comment in recent_comments
        ],
        "comment_count": (fields.get("comment") or {}).get("total", len(comments)),
    }


def adf_text(node: Any) -> str:
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return " ".join(" ".join(part for part in (adf_text(item) for item in node) if part).split())
    if isinstance(node, dict):
        if node.get("type") == "mention":
            return str((node.get("attrs") or {}).get("text") or "")
        own = str(node.get("text") or "")
        nested = adf_text(node.get("content") or [])
        return " ".join(part for part in (own, nested) if part)
    return str(node)


def comment_doc(comment: str, mention_account_id: str | None = None, mention_display_name: str | None = None) -> dict[str, Any]:
    content: list[dict[str, Any]] = []
    if mention_account_id:
        display = mention_display_name or "Jira user"
        content.append({
            "type": "mention",
            "attrs": {"id": mention_account_id, "text": f"@{display}", "userType": "APP"},
        })
        if comment.strip():
            content.append({"type": "text", "text": f" {comment.strip()}"})
    else:
        content.append({"type": "text", "text": comment})
    return {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": content}]}
