from __future__ import annotations

import base64
from typing import Any

from .codex_auth_common import AuthConfigError, import_dependency, load_env_file, optional_env, require_env


def base_url() -> str:
    load_env_file("jira.env")
    return require_env(("JIRA_BASE_URL",))["JIRA_BASE_URL"].rstrip("/")


def auth_headers() -> dict[str, str]:
    load_env_file("jira.env")
    require_env(("JIRA_BASE_URL",))
    oauth_token = optional_env("JIRA_OAUTH_ACCESS_TOKEN")
    pat = optional_env("JIRA_PAT")
    email = optional_env("JIRA_EMAIL")
    api_token = optional_env("JIRA_API_TOKEN")
    if oauth_token:
        return {"Authorization": f"Bearer {oauth_token}", "Accept": "application/json"}
    if pat:
        return {"Authorization": f"Bearer {pat}", "Accept": "application/json"}
    if email and api_token:
        raw = f"{email}:{api_token}".encode("utf-8")
        encoded = base64.b64encode(raw).decode("ascii")
        return {"Authorization": f"Basic {encoded}", "Accept": "application/json"}
    raise AuthConfigError("Missing Jira auth. Set JIRA_OAUTH_ACCESS_TOKEN, JIRA_PAT, or JIRA_EMAIL plus JIRA_API_TOKEN.")


def session() -> Any:
    requests = import_dependency("requests", "python -m pip install requests")
    client = requests.Session()
    client.headers.update(auth_headers())
    return client
