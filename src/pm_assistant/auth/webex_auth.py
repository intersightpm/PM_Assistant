from __future__ import annotations

from typing import Any

from .codex_auth_common import import_dependency, load_env_file, require_env

WEBEX_BASE = "https://webexapis.com/v1"
TOKEN_URL = f"{WEBEX_BASE}/access_token"


def refresh_access_token() -> str:
    load_env_file("webex.env")
    env = require_env(("WEBEX_CLIENT_ID", "WEBEX_CLIENT_SECRET", "WEBEX_REFRESH_TOKEN", "WEBEX_REDIRECT_URI"))
    requests = import_dependency("requests", "python -m pip install requests")
    response = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "refresh_token",
            "client_id": env["WEBEX_CLIENT_ID"],
            "client_secret": env["WEBEX_CLIENT_SECRET"],
            "refresh_token": env["WEBEX_REFRESH_TOKEN"],
            "redirect_uri": env["WEBEX_REDIRECT_URI"],
        },
        timeout=30,
    )
    response.raise_for_status()
    return str(response.json()["access_token"])


def auth_headers() -> dict[str, str]:
    token = refresh_access_token()
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def session() -> Any:
    requests = import_dependency("requests", "python -m pip install requests")
    client = requests.Session()
    client.headers.update(auth_headers())
    return client

