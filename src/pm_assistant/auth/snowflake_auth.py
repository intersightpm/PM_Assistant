from __future__ import annotations

from pathlib import Path
from typing import Any

from .codex_auth_common import AuthConfigError, import_dependency, load_env_file, optional_env, require_env


def connection_kwargs() -> dict[str, Any]:
    load_env_file("snowflake.env")
    env = require_env(("SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER"))
    kwargs: dict[str, Any] = {
        "account": env["SNOWFLAKE_ACCOUNT"],
        "user": env["SNOWFLAKE_USER"],
    }
    for env_name, key in (
        ("SNOWFLAKE_WAREHOUSE", "warehouse"),
        ("SNOWFLAKE_DATABASE", "database"),
        ("SNOWFLAKE_SCHEMA", "schema"),
        ("SNOWFLAKE_ROLE", "role"),
    ):
        value = optional_env(env_name)
        if value:
            kwargs[key] = value

    password = optional_env("SNOWFLAKE_PASSWORD")
    private_key_path = optional_env("SNOWFLAKE_PRIVATE_KEY_PATH")
    if password:
        kwargs["password"] = password
    elif private_key_path:
        kwargs["private_key"] = _load_private_key(private_key_path)
    else:
        raise AuthConfigError("Missing Snowflake auth. Set SNOWFLAKE_PASSWORD or SNOWFLAKE_PRIVATE_KEY_PATH.")
    return kwargs


def connect() -> Any:
    connector = import_dependency("snowflake.connector", "python -m pip install snowflake-connector-python")
    return connector.connect(**connection_kwargs())


def test_connection() -> dict[str, Any]:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT CURRENT_USER(), CURRENT_ROLE(), CURRENT_WAREHOUSE(), CURRENT_DATABASE(), CURRENT_SCHEMA()")
            user, role, warehouse, database, schema = cur.fetchone()
    return {
        "user": user,
        "role": role,
        "warehouse": warehouse,
        "database": database,
        "schema": schema,
    }


def _load_private_key(path_value: str) -> bytes:
    serialization = import_dependency("cryptography.hazmat.primitives.serialization", "python -m pip install cryptography")
    key_path = Path(path_value).expanduser()
    if not key_path.exists():
        raise AuthConfigError(f"Snowflake private key file does not exist: {key_path}")
    passphrase = optional_env("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")
    password = passphrase.encode("utf-8") if passphrase else None
    private_key = serialization.load_pem_private_key(key_path.read_bytes(), password=password)
    return private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

