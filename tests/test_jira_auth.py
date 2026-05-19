from __future__ import annotations

import base64
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pm_assistant.auth.jira_auth import auth_headers, base_url


def test_jira_regular_api_token_headers(tmp_path: Path, monkeypatch) -> None:
    central = tmp_path / "central"
    central.mkdir()
    (central / "jira.env").write_text(
        "\n".join(
            (
                "JIRA_BASE_URL=https://example.atlassian.net",
                "JIRA_EMAIL=user@example.com",
                "JIRA_API_TOKEN=abc123",
                "JIRA_OAUTH_ACCESS_TOKEN=",
                "JIRA_PAT=",
            )
        ),
        encoding="utf-8",
    )
    for key in ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_OAUTH_ACCESS_TOKEN", "JIRA_PAT"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CODEX_AUTH_SECRETS_DIR", str(central))
    monkeypatch.setenv("CODEX_AUTH_PROJECT_DIR", str(tmp_path / "project"))

    headers = auth_headers()

    expected = base64.b64encode(b"user@example.com:abc123").decode("ascii")
    assert base_url() == "https://example.atlassian.net"
    assert headers["Authorization"] == f"Basic {expected}"
    assert headers["Accept"] == "application/json"

