from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pm_assistant.auth.codex_auth_common import AuthConfigError, load_env_file, require_env


TEST_KEYS = ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (*TEST_KEYS, "CODEX_AUTH_SECRETS_DIR", "CODEX_AUTH_PROJECT_DIR"):
        monkeypatch.delenv(key, raising=False)


def write_env(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8")


def test_project_local_file_wins_when_valid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    central = tmp_path / "central"
    project = tmp_path / "project"
    write_env(project / "jira.env", {"JIRA_BASE_URL": "https://local.atlassian.net"})
    write_env(central / "jira.env", {"JIRA_BASE_URL": "https://central.atlassian.net"})
    monkeypatch.setenv("CODEX_AUTH_SECRETS_DIR", str(central))
    monkeypatch.setenv("CODEX_AUTH_PROJECT_DIR", str(project))

    load_env_file("jira.env")

    assert os.environ["JIRA_BASE_URL"] == "https://local.atlassian.net"


def test_local_service_env_used_when_central_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "project"
    write_env(project / "jira.env", {"JIRA_BASE_URL": "https://local.atlassian.net"})
    monkeypatch.setenv("CODEX_AUTH_SECRETS_DIR", str(tmp_path / "missing-central"))
    monkeypatch.setenv("CODEX_AUTH_PROJECT_DIR", str(project))

    load_env_file("jira.env")

    assert os.environ["JIRA_BASE_URL"] == "https://local.atlassian.net"


def test_local_env_used_when_central_has_placeholder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    central = tmp_path / "central"
    project = tmp_path / "project"
    write_env(project / ".env", {"JIRA_BASE_URL": "https://local-dotenv.atlassian.net"})
    write_env(central / "jira.env", {"JIRA_BASE_URL": "your-company.atlassian.net"})
    monkeypatch.setenv("CODEX_AUTH_SECRETS_DIR", str(central))
    monkeypatch.setenv("CODEX_AUTH_PROJECT_DIR", str(project))

    load_env_file("jira.env")

    assert os.environ["JIRA_BASE_URL"] == "https://local-dotenv.atlassian.net"


def test_process_environment_used_when_no_file_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODEX_AUTH_SECRETS_DIR", str(tmp_path / "missing-central"))
    monkeypatch.setenv("CODEX_AUTH_PROJECT_DIR", str(tmp_path / "missing-project"))
    monkeypatch.setenv("JIRA_BASE_URL", "https://process.atlassian.net")

    load_env_file("jira.env")

    assert require_env(("JIRA_BASE_URL",))["JIRA_BASE_URL"] == "https://process.atlassian.net"


def test_placeholder_values_fail_required_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JIRA_API_TOKEN", "REPLACE_ME")

    with pytest.raises(AuthConfigError, match="JIRA_API_TOKEN"):
        require_env(("JIRA_API_TOKEN",))
