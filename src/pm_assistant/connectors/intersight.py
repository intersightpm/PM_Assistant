from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from pm_assistant.auth import intersight_auth
from pm_assistant.core.storage import RUNS_DIR

OBJECT_PATHS = {
    "iam/Accounts": "/api/v1/iam/Accounts",
    "organization/Organizations": "/api/v1/organization/Organizations",
    "compute/PhysicalSummaries": "/api/v1/compute/PhysicalSummaries",
    "equipment/Chasses": "/api/v1/equipment/Chasses",
    "network/Elements": "/api/v1/network/Elements",
    "asset/DeviceRegistrations": "/api/v1/asset/DeviceRegistrations",
    "cond/Alarms": "/api/v1/cond/Alarms",
    "cond/Advisories": "/api/v1/cond/Advisories",
}
INVENTORY_OBJECT_TYPES = (
    "iam/Accounts",
    "organization/Organizations",
    "compute/PhysicalSummaries",
    "equipment/Chasses",
    "network/Elements",
    "asset/DeviceRegistrations",
)
HEALTH_OBJECT_TYPES = ("cond/Alarms", "cond/Advisories")


def account_list(account: str = "all") -> list[str]:
    normalized = intersight_auth.normalize_account(account)
    return list(intersight_auth.KNOWN_ACCOUNTS) if normalized == "all" else [normalized]


def query(account: str, object_type: str, filters: dict[str, Any] | str | None = None, top: int = 100) -> dict[str, Any]:
    path = object_path(object_type)
    params: dict[str, Any] = {"$top": max(1, min(int(top), 1000))}
    filter_text = filter_expression(filters)
    if filter_text:
        params["$filter"] = filter_text
    return get(account, add_query(path, params))


def get(account: str, path: str) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for profile in account_list(account):
        try:
            payload = get_all_pages(profile, path)
            records = extract_records(payload)
            results[profile] = {
                "ok": True,
                "account": profile,
                "path": path,
                "count": len(records),
                "truncated": is_likely_truncated(path, len(records)),
                "records": records,
            }
        except Exception as exc:
            results[profile] = {"ok": False, "account": profile, "path": path, "error": str(exc), "records": []}
    return {"accounts": results, "merged_count": sum(len(item.get("records") or []) for item in results.values())}


def count(account: str, object_type: str, filters: dict[str, Any] | str | None = None) -> dict[str, Any]:
    result = query(account, object_type, filters=filters, top=1000)
    return {
        "object_type": object_type,
        "accounts": {
            profile: {
                "ok": data.get("ok", False),
                "count": len(data.get("records") or []),
                "truncated": data.get("truncated", False),
                **({"error": data.get("error")} if data.get("error") else {}),
            }
            for profile, data in result["accounts"].items()
        },
        "merged_count": result["merged_count"],
    }


def inventory_summary(account: str = "all", save: bool = False, runs_dir: Path = RUNS_DIR) -> dict[str, Any]:
    summary = source_summary(account, INVENTORY_OBJECT_TYPES, purpose="inventory")
    return save_summary(summary, "intersight_inventory", runs_dir) if save else summary


def health_summary(account: str = "all", save: bool = False, runs_dir: Path = RUNS_DIR) -> dict[str, Any]:
    summary = source_summary(account, HEALTH_OBJECT_TYPES, purpose="health")
    return save_summary(summary, "intersight_health", runs_dir) if save else summary


def impact_analysis(account: str = "all", criteria: dict[str, Any] | None = None, save: bool = False, runs_dir: Path = RUNS_DIR) -> dict[str, Any]:
    criteria = criteria or {}
    object_types = criteria.get("object_types") or ["compute/PhysicalSummaries"]
    filters = criteria.get("filters")
    accounts: dict[str, Any] = {}
    for object_type in object_types:
        accounts[object_type] = query(account, object_type, filters=filters, top=int(criteria.get("top") or 1000))
    summary = {
        "schema_version": 1,
        "artifact_type": "intersight_impact",
        "created_at": utc_now_iso(),
        "account": account,
        "criteria": criteria,
        "results": accounts,
        "warnings": partial_failure_warnings(accounts),
    }
    return save_summary(summary, "intersight_impact", runs_dir) if save else summary


def adoption_signals(topic: str, account: str = "all") -> dict[str, Any]:
    inventory = inventory_summary(account=account, save=False)
    health = health_summary(account=account, save=False)
    return {
        "source": "intersight",
        "topic": topic,
        "account": account,
        "signals": {
            "managed_assets": inventory.get("merged_counts", {}),
            "health_friction": health.get("merged_counts", {}),
        },
        "source_summaries": {
            "inventory": compact_summary(inventory),
            "health": compact_summary(health),
        },
        "warnings": [*inventory.get("warnings", []), *health.get("warnings", [])],
    }


def source_summary(account: str, object_types: tuple[str, ...], purpose: str) -> dict[str, Any]:
    results: dict[str, Any] = {}
    merged_counts: dict[str, int] = {}
    for object_type in object_types:
        result = query(account, object_type, top=1000)
        results[object_type] = {
            profile: {
                "ok": data.get("ok", False),
                "count": len(data.get("records") or []),
                "truncated": data.get("truncated", False),
                "records": [normalize_record(record, profile, object_type) for record in data.get("records") or []],
                **({"error": data.get("error")} if data.get("error") else {}),
            }
            for profile, data in result["accounts"].items()
        }
        merged_counts[object_type] = result["merged_count"]
    summary = {
        "schema_version": 1,
        "artifact_type": f"intersight_{purpose}",
        "created_at": utc_now_iso(),
        "account": account,
        "object_types": list(object_types),
        "merged_counts": merged_counts,
        "results": results,
        "warnings": partial_failure_warnings(results),
    }
    summary["warnings"].extend(truncation_warnings(results))
    return summary


def get_all_pages(account: str, path: str) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    next_path: str | None = path
    while next_path:
        response = intersight_auth.get(next_path, account=account, timeout=30)
        response.raise_for_status()
        payload = response.json()
        payloads.append(payload)
        next_link = next_page_link(payload)
        next_path = next_link if next_link and len(payloads) < 10 else None
    return payloads


def extract_records(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for payload in payloads:
        if isinstance(payload, dict):
            for key in ("Results", "results", "Items", "items"):
                value = payload.get(key)
                if isinstance(value, list):
                    records.extend(item for item in value if isinstance(item, dict))
                    break
        elif isinstance(payload, list):
            records.extend(item for item in payload if isinstance(item, dict))
    return records


def normalize_record(record: dict[str, Any], account: str, object_type: str) -> dict[str, Any]:
    return {
        "account": account,
        "object_type": object_type,
        "moid": value(record, "Moid", "moid"),
        "name": value(record, "Name", "name", "DeviceHostname", "Hostname"),
        "serial": value(record, "Serial", "SerialNumber", "DeviceSerialNumber"),
        "model": value(record, "Model", "Pid", "ProductName"),
        "status": value(record, "OperState", "ConnectionStatus", "Status"),
        "health": value(record, "Health", "HealthStatus", "AlarmSummary"),
        "organization": nested_value(record, ("Organization", "Name")) or nested_value(record, ("RegisteredDevice", "Name")),
        "source_path": object_path(object_type),
        "raw": compact_raw(record),
    }


def compact_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_type": summary.get("artifact_type"),
        "account": summary.get("account"),
        "merged_counts": summary.get("merged_counts", {}),
        "warnings": summary.get("warnings", []),
    }


def compact_raw(record: dict[str, Any]) -> dict[str, Any]:
    allowed = (
        "Moid",
        "Name",
        "Model",
        "Serial",
        "SerialNumber",
        "OperState",
        "ConnectionStatus",
        "Health",
        "HealthStatus",
        "Severity",
        "Description",
        "CreateTime",
        "ModTime",
    )
    return {key: record.get(key) for key in allowed if key in record}


def object_path(object_type: str) -> str:
    normalized = object_type.strip().strip("/")
    return OBJECT_PATHS.get(normalized, f"/api/v1/{normalized}")


def add_query(path: str, params: dict[str, Any]) -> str:
    separator = "&" if "?" in path else "?"
    return f"{path}{separator}{urlencode(params)}" if params else path


def filter_expression(filters: dict[str, Any] | str | None) -> str:
    if not filters:
        return ""
    if isinstance(filters, str):
        return filters
    expressions = []
    for key, raw_value in filters.items():
        if not re.fullmatch(r"[A-Za-z0-9_.]+", str(key)):
            raise ValueError(f"Unsafe Intersight filter field: {key}")
        if isinstance(raw_value, bool):
            value_text = "true" if raw_value else "false"
        elif isinstance(raw_value, (int, float)):
            value_text = str(raw_value)
        else:
            escaped = str(raw_value).replace("'", "''")
            value_text = f"'{escaped}'"
        expressions.append(f"{key} eq {value_text}")
    return " and ".join(expressions)


def partial_failure_warnings(results: dict[str, Any]) -> list[str]:
    warnings = []
    for key, value_data in results.items():
        if isinstance(value_data, dict) and "accounts" in value_data:
            iterable = value_data["accounts"].items()
        elif isinstance(value_data, dict):
            iterable = value_data.items()
        else:
            continue
        for account, account_data in iterable:
            if isinstance(account_data, dict) and not account_data.get("ok", True):
                warnings.append(f"{key}/{account}: {account_data.get('error')}")
    return warnings


def save_summary(summary: dict[str, Any], prefix: str, runs_dir: Path = RUNS_DIR) -> dict[str, Any]:
    run_id = f"{prefix}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / f"{prefix}.json"
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8", newline="\n")
    return {"run_id": run_id, "path": str(path), **summary}


def next_page_link(payload: dict[str, Any]) -> str | None:
    next_link = payload.get("Next") or payload.get("next")
    return str(next_link) if next_link else None


def is_likely_truncated(path: str, count: int) -> bool:
    match = re.search(r"(?:%24top|\$top)=(\d+)", path)
    if not match:
        return False
    try:
        return count >= int(match.group(1))
    except ValueError:
        return False


def truncation_warnings(results: dict[str, Any]) -> list[str]:
    warnings = []
    for object_type, account_results in results.items():
        if not isinstance(account_results, dict):
            continue
        for account, data in account_results.items():
            if isinstance(data, dict) and data.get("truncated"):
                warnings.append(f"{object_type}/{account}: result reached the page cap; counts are lower-bound previews.")
    return warnings


def value(record: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if record.get(key) not in (None, ""):
            return record[key]
    return None


def nested_value(record: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = record
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def count_by(records: list[dict[str, Any]], field: str) -> dict[str, int]:
    return dict(Counter(str(record.get(field) or "Unknown") for record in records))


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
