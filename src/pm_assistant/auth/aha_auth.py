from __future__ import annotations

from typing import Any

from .codex_auth_common import import_dependency, load_env_file, optional_env, require_env


def base_url() -> str:
    load_env_file("aha.env")
    domain = require_env(("AHA_DOMAIN",))["AHA_DOMAIN"].replace("https://", "").strip("/")
    return f"https://{domain}/api/v1"


def auth_headers() -> dict[str, str]:
    load_env_file("aha.env")
    token = require_env(("AHA_TOKEN",))["AHA_TOKEN"]
    user_agent = optional_env("AHA_USER_AGENT", "codex-shared-auth") or "codex-shared-auth"
    return {"Authorization": f"Bearer {token}", "User-Agent": user_agent, "Accept": "application/json"}


def session() -> Any:
    requests = import_dependency("requests", "python -m pip install requests")
    client = requests.Session()
    client.headers.update(auth_headers())
    return client

