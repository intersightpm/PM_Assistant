from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

CODEX_HOME = Path.home() / ".codex"
DEFAULT_SECRETS_DIR = CODEX_HOME / "secrets"
SECRETS_DIR_ENV = "CODEX_AUTH_SECRETS_DIR"
PROJECT_DIR_ENV = "CODEX_AUTH_PROJECT_DIR"

PLACEHOLDER_PREFIXES = ("your_", "your-", "todo", "replace", "changeme", "xxx")
PLACEHOLDER_VALUES = {"", "todo", "replace_me", "changeme", "xxx", "<redacted>"}


class AuthConfigError(RuntimeError):
    """Raised when a shared auth helper cannot load or validate credentials."""


def secrets_dir() -> Path:
    override = os.getenv(SECRETS_DIR_ENV)
    return Path(override).expanduser() if override else DEFAULT_SECRETS_DIR


def secret_path(filename: str) -> Path:
    return secrets_dir() / filename


def load_env_file(filename: str, *, override: bool = False) -> dict[str, str]:
    """Load env values for a service.

    Precedence is project-local env files, then optional central Codex secrets,
    then existing process environment. Placeholder values are treated as missing.
    """

    loaded: dict[str, str] = {}
    for path in _candidate_paths(filename):
        if not path.exists():
            continue
        for key, value in _read_env_file(path).items():
            if _is_placeholder(value):
                continue
            os.environ[key] = value
            loaded[key] = os.environ[key]
    return loaded


def require_env(names: Iterable[str]) -> dict[str, str]:
    missing = [name for name in names if _is_placeholder(os.getenv(name))]
    if missing:
        raise AuthConfigError(f"Missing required environment variables: {', '.join(missing)}")
    return {name: os.environ[name] for name in names}


def optional_env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return value if not _is_placeholder(value) else default


def require_any(groups: Iterable[Iterable[str]], message: str) -> dict[str, str]:
    for group in groups:
        names = list(group)
        if all(not _is_placeholder(os.getenv(name)) for name in names):
            return {name: os.environ[name] for name in names}
    raise AuthConfigError(message)


def import_dependency(module_name: str, install_hint: str):
    try:
        return __import__(module_name, fromlist=["*"])
    except ImportError as exc:
        raise AuthConfigError(f"Missing optional dependency '{module_name}'. Install with: {install_hint}") from exc


def _candidate_paths(filename: str) -> list[Path]:
    local_paths: list[Path] = []
    for directory in _project_dirs():
        local_paths.extend((directory / ".env", directory / filename))

    # Load lower-priority file sources first so project-local values override
    # central secrets and existing process variables.
    paths = [secret_path(filename), *reversed(local_paths)]
    unique: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.expanduser().resolve(strict=False)
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return unique


def _project_dirs() -> list[Path]:
    start = Path(os.getenv(PROJECT_DIR_ENV) or Path.cwd()).expanduser().resolve(strict=False)
    dirs = [start]
    for parent in start.parents:
        dirs.append(parent)
        if parent == Path.home().resolve(strict=False):
            break
    return dirs


def _read_env_file(path: Path) -> dict[str, str]:
    loaded: dict[str, str] = {}
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("export "):
                line = line[7:].strip()
            if "=" not in line:
                raise AuthConfigError(f"Invalid env line in {path} at line {line_number}: expected KEY=value")
            key, value = line.split("=", 1)
            key = key.strip()
            value = _strip_env_value(value.strip())
            if not key:
                raise AuthConfigError(f"Invalid env line in {path} at line {line_number}: empty key")
            loaded[key] = value
    return loaded


def _strip_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _is_placeholder(value: str | None) -> bool:
    if value is None:
        return True
    normalized = value.strip().lower()
    return normalized in PLACEHOLDER_VALUES or normalized.startswith(PLACEHOLDER_PREFIXES)
