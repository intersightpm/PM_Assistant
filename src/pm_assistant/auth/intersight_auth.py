from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from .codex_auth_common import AuthConfigError, import_dependency, load_env_file, optional_env, require_env

DEFAULT_BASE_URL = "https://intersight.com"
DEFAULT_ACCOUNT = "default"
KNOWN_ACCOUNTS = ("us", "eu")
INTERSIGHT_ENV_VARS = (
    "INTERSIGHT_BASE_URL",
    "INTERSIGHT_API_KEY_ID",
    "INTERSIGHT_PRIVATE_KEY",
    "INTERSIGHT_PRIVATE_KEY_PATH",
)


def profile_env_filename(account: str | None = None) -> str:
    normalized = normalize_account(account)
    return "intersight.env" if normalized == DEFAULT_ACCOUNT else f"intersight-{normalized}.env"


def normalize_account(account: str | None = None) -> str:
    normalized = (account or DEFAULT_ACCOUNT).strip().lower()
    return normalized or DEFAULT_ACCOUNT


def load_profile_environment(account: str | None = None) -> str:
    filename = profile_env_filename(account)
    for name in INTERSIGHT_ENV_VARS:
        os.environ.pop(name, None)
    load_env_file(filename)
    return filename


def base_url(account: str | None = None) -> str:
    load_profile_environment(account)
    return (optional_env("INTERSIGHT_BASE_URL", DEFAULT_BASE_URL) or DEFAULT_BASE_URL).rstrip("/")


def signed_headers(method: str, path: str, body: bytes | str | None = None, account: str | None = None) -> dict[str, str]:
    load_profile_environment(account)
    key_id = require_env(("INTERSIGHT_API_KEY_ID",))["INTERSIGHT_API_KEY_ID"]
    private_key = _load_private_key()
    host = urlparse(base_url(account)).netloc
    parsed_body = _body_bytes(body)
    digest = "SHA-256=" + base64.b64encode(hashlib.sha256(parsed_body).digest()).decode("ascii")
    date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
    request_target = f"{method.lower()} {path}"
    signing_string = f"(request-target): {request_target}\nhost: {host}\ndate: {date}\ndigest: {digest}"
    algorithm, signature = _sign(private_key, signing_string.encode("utf-8"))
    authorization = (
        f'Signature keyId="{key_id}",algorithm="{algorithm}",'
        f'headers="(request-target) host date digest",signature="{signature}"'
    )
    return {"Authorization": authorization, "Host": host, "Date": date, "Digest": digest, "Accept": "application/json"}


@dataclass
class IntersightSession:
    base_url: str
    client: Any
    account: str = DEFAULT_ACCOUNT

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        body = kwargs.get("data") or kwargs.get("json") or b""
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.update(signed_headers(method, path, body, account=self.account))
        url = urljoin(f"{self.base_url}/", path.lstrip("/"))
        return self.client.request(method, url, headers=headers, **kwargs)

    def get(self, path: str, **kwargs: Any) -> Any:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Any:
        return self.request("POST", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> Any:
        return self.request("PATCH", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Any:
        return self.request("DELETE", path, **kwargs)


def session(account: str | None = None) -> IntersightSession:
    requests = import_dependency("requests", "python -m pip install requests")
    normalized = normalize_account(account)
    return IntersightSession(base_url=base_url(normalized), client=requests.Session(), account=normalized)


def get(path: str, account: str | None = None, **kwargs: Any) -> Any:
    return session(account).get(path, **kwargs)


def connection_summary(account: str | None = None, path: str = "/api/v1/iam/Accounts") -> dict[str, Any]:
    normalized = normalize_account(account)
    response = get(path, account=normalized, timeout=30)
    response.raise_for_status()
    payload = response.json()
    return {
        "account": normalized,
        "base_url": base_url(normalized),
        "path": path,
        "status_code": response.status_code,
        "result_count": _result_count(payload),
    }


def connection_summaries(account: str = "all", path: str = "/api/v1/iam/Accounts") -> dict[str, Any]:
    accounts = list(KNOWN_ACCOUNTS) if normalize_account(account) == "all" else [normalize_account(account)]
    results: dict[str, Any] = {}
    for profile in accounts:
        try:
            results[profile] = {"ok": True, **connection_summary(profile, path=path)}
        except Exception as exc:
            results[profile] = {"ok": False, "account": profile, "error": str(exc)}
    return results


def _result_count(payload: Any) -> int | None:
    if isinstance(payload, dict):
        for key in ("Results", "results", "Items", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return len(value)
        if isinstance(payload.get("Count"), int):
            return payload["Count"]
    if isinstance(payload, list):
        return len(payload)
    return None


def _load_private_key() -> Any:
    serialization = import_dependency("cryptography.hazmat.primitives.serialization", "python -m pip install cryptography")
    pem = optional_env("INTERSIGHT_PRIVATE_KEY")
    key_path = optional_env("INTERSIGHT_PRIVATE_KEY_PATH")
    if pem:
        data = pem.replace("\\n", "\n").encode("utf-8-sig")
    elif key_path:
        path = Path(key_path).expanduser()
        if not path.exists():
            raise AuthConfigError(f"Intersight private key file does not exist: {path}")
        data = path.read_bytes()
        if data.startswith(b"\xef\xbb\xbf"):
            data = data[3:]
    else:
        raise AuthConfigError("Missing Intersight private key. Set INTERSIGHT_PRIVATE_KEY_PATH or INTERSIGHT_PRIVATE_KEY.")
    return _load_pem_private_key(serialization, data)


def _load_pem_private_key(serialization: Any, data: bytes) -> Any:
    try:
        return serialization.load_pem_private_key(data, password=None)
    except ValueError:
        text = data.decode("utf-8", errors="ignore")
        if "BEGIN EC PRIVATE KEY" not in text:
            raise
        normalized = (
            text.replace("-----BEGIN EC PRIVATE KEY-----", "-----BEGIN PRIVATE KEY-----")
            .replace("-----END EC PRIVATE KEY-----", "-----END PRIVATE KEY-----")
            .encode("utf-8")
        )
        return serialization.load_pem_private_key(normalized, password=None)


def _sign(private_key: Any, payload: bytes) -> tuple[str, str]:
    hashes = import_dependency("cryptography.hazmat.primitives.hashes", "python -m pip install cryptography")
    padding = import_dependency("cryptography.hazmat.primitives.asymmetric.padding", "python -m pip install cryptography")
    rsa = import_dependency("cryptography.hazmat.primitives.asymmetric.rsa", "python -m pip install cryptography")
    ec = import_dependency("cryptography.hazmat.primitives.asymmetric.ec", "python -m pip install cryptography")
    if isinstance(private_key, rsa.RSAPrivateKey):
        signature = private_key.sign(payload, padding.PKCS1v15(), hashes.SHA256())
        return "rsa-sha256", base64.b64encode(signature).decode("ascii")
    if isinstance(private_key, ec.EllipticCurvePrivateKey):
        signature = private_key.sign(payload, ec.ECDSA(hashes.SHA256()))
        return "hs2019", base64.b64encode(signature).decode("ascii")
    raise AuthConfigError(f"Unsupported Intersight private key type: {type(private_key).__name__}")


def _body_bytes(body: bytes | str | None) -> bytes:
    if body is None:
        return b""
    if isinstance(body, bytes):
        return body
    return str(body).encode("utf-8")
