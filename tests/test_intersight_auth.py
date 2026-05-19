from pathlib import Path

from pm_assistant.auth import intersight_auth


def write_env(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8")


def test_profile_env_filename():
    assert intersight_auth.profile_env_filename() == "intersight.env"
    assert intersight_auth.profile_env_filename("default") == "intersight.env"
    assert intersight_auth.profile_env_filename("us") == "intersight-us.env"
    assert intersight_auth.profile_env_filename("eu") == "intersight-eu.env"


def test_profile_loading_clears_previous_values(tmp_path, monkeypatch):
    secrets = tmp_path / "secrets"
    write_env(secrets / "intersight-us.env", {
        "INTERSIGHT_BASE_URL": "https://us.example.com",
        "INTERSIGHT_API_KEY_ID": "us-key",
        "INTERSIGHT_PRIVATE_KEY": "us-private",
    })
    write_env(secrets / "intersight-eu.env", {
        "INTERSIGHT_BASE_URL": "https://eu.example.com",
        "INTERSIGHT_API_KEY_ID": "eu-key",
        "INTERSIGHT_PRIVATE_KEY_PATH": "eu.pem",
    })
    monkeypatch.setenv("CODEX_AUTH_SECRETS_DIR", str(secrets))
    monkeypatch.setenv("CODEX_AUTH_PROJECT_DIR", str(tmp_path / "project"))

    intersight_auth.load_profile_environment("us")
    assert intersight_auth.optional_env("INTERSIGHT_PRIVATE_KEY") == "us-private"

    intersight_auth.load_profile_environment("eu")
    assert intersight_auth.optional_env("INTERSIGHT_API_KEY_ID") == "eu-key"
    assert intersight_auth.optional_env("INTERSIGHT_PRIVATE_KEY") is None
    assert intersight_auth.optional_env("INTERSIGHT_PRIVATE_KEY_PATH") == "eu.pem"


def test_connection_summaries_handles_all_accounts(monkeypatch):
    def fake_summary(account, path="/api/v1/iam/Accounts"):
        return {"account": account, "path": path, "status_code": 200, "result_count": 1}

    monkeypatch.setattr(intersight_auth, "connection_summary", fake_summary)

    result = intersight_auth.connection_summaries("all")

    assert result["us"]["ok"]
    assert result["eu"]["ok"]
    assert result["us"]["account"] == "us"
    assert result["eu"]["account"] == "eu"


def test_connection_summary_uses_signed_get(monkeypatch):
    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"Results": [{"Name": "Account"}]}

    monkeypatch.setattr(intersight_auth, "get", lambda path, account=None, timeout=30: FakeResponse())
    monkeypatch.setattr(intersight_auth, "base_url", lambda account=None: "https://intersight.example.com")

    result = intersight_auth.connection_summary("us")

    assert result["account"] == "us"
    assert result["status_code"] == 200
    assert result["result_count"] == 1
