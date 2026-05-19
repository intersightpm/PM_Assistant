from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone
from typing import Any

import requests

from pm_assistant.core.matching import text_matches_feature
from pm_assistant.core.models import Evidence, FeatureConfig

from .base import Connector, ConnectorResult


class AhaConnector(Connector):
    name = "aha"

    def __init__(self) -> None:
        self.domain = (os.getenv("AHA_DOMAIN") or "").replace("https://", "").strip("/")
        self.token = os.getenv("AHA_TOKEN") or ""
        self.user_agent = os.getenv("AHA_USER_AGENT") or "pm-assistant"
        self.customer_record_cache: dict[str, str] = {}
        self.forbidden_customer_records: set[str] = set()

    @property
    def base_url(self) -> str:
        return f"https://{self.domain}/api/v1"

    def configured(self) -> tuple[bool, str]:
        if not self.domain:
            return False, "AHA_DOMAIN is missing. Set it to your Aha domain, for example company.aha.io."
        if "." not in self.domain:
            return False, "AHA_DOMAIN should look like company.aha.io and should not include https://."
        if not self.token:
            return False, "AHA_TOKEN is missing. Create an Aha API key and set it in .env."
        return True, "Aha credentials are present."

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "User-Agent": self.user_agent, "Accept": "application/json"}

    def request_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        for attempt in range(3):
            response = requests.get(url, headers=self.headers(), params=params, timeout=30)
            if response.status_code == 429 and attempt < 2:
                reset = response.headers.get("X-Ratelimit-Reset")
                sleep_for = 2
                if reset and reset.isdigit():
                    sleep_for = max(1, min(30, int(reset) - int(time.time())))
                time.sleep(sleep_for)
                continue
            response.raise_for_status()
            return response.json()
        response.raise_for_status()
        return {}

    def doctor(self) -> ConnectorResult:
        ok, message = self.configured()
        if not ok:
            return ConnectorResult(warnings=[message])
        try:
            self.request_json("/ideas", {"page": 1, "per_page": 1})
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            return ConnectorResult(warnings=[f"Aha API check failed with HTTP {status}. Verify AHA_DOMAIN, AHA_TOKEN, and idea access."])
        except requests.RequestException as exc:
            return ConnectorResult(warnings=[f"Aha API check failed: {exc}"])
        return ConnectorResult(warnings=["Aha API check passed."])

    def collect(self, config: FeatureConfig, date_range: str | None = None) -> ConnectorResult:
        ok, message = self.configured()
        if not ok:
            return ConnectorResult(warnings=[message])
        evidence: list[Evidence] = []
        warnings: list[str] = []
        filters = config.source_filters or {}
        collection_profile = str(filters.get("collection_profile") or "accuracy").lower()
        collect_comments = bool(filters.get("aha_collect_comments", collection_profile != "fast"))
        max_pages = int(filters.get("aha_max_pages") or 0)
        time_budget_seconds = int(filters.get("aha_time_budget_seconds") or 0)
        started = time.monotonic()
        range_start = date_range_start(date_range)
        page = 1
        pages_scanned = 0
        while True:
            if max_pages and page > max_pages:
                warnings.append(f"Aha collection stopped after configured max pages ({max_pages}).")
                break
            if time_budget_seconds and time.monotonic() - started > time_budget_seconds:
                warnings.append(f"Aha collection stopped after configured time budget ({time_budget_seconds}s).")
                break
            try:
                params: dict[str, Any] = {"page": page, "per_page": 100}
                if range_start:
                    params["updated_since"] = range_start.isoformat().replace("+00:00", "Z")
                progress(f"[aha] fetching ideas page {page}")
                data = self.request_json("/ideas", params)
            except requests.RequestException as exc:
                warnings.append(f"Aha collection stopped on page {page}: {exc}")
                break
            ideas = data.get("ideas") or data.get("records") or []
            pages_scanned = page
            progress(f"[aha] page {page}: {len(ideas)} ideas")
            for idea in ideas:
                if range_start and idea_created_before(idea, range_start):
                    continue
                item = self.idea_to_evidence(idea)
                item_matches = text_matches_feature(f"{item.title}\n{item.text}", config)
                if item_matches:
                    reference = str(idea.get("reference_num") or idea.get("id") or "")
                    detail_idea = self.idea_detail_for_metadata(reference, warnings, idea)
                    self.add_opportunity_value_metadata(item, detail_idea)
                    customers = self.collect_idea_customers(reference, warnings, detail_idea, allow_detail_fetch=False)
                    if customers:
                        item.requester = ", ".join(customers)
                        item.source_metadata["idea_customers"] = customers
                    evidence.append(item)
                if collect_comments and item_matches:
                    evidence.extend(self.collect_matching_comments(idea, config, warnings))
            if not ideas or page >= pagination_total_pages(data):
                break
            page += 1
        return ConnectorResult(evidence=evidence, warnings=warnings, metadata={
            "pages_scanned": pages_scanned,
            "comments_enabled": collect_comments,
            "max_pages": max_pages,
            "time_budget_seconds": time_budget_seconds,
            "customer_records_cached": len(self.customer_record_cache),
            "forbidden_customer_records": len(self.forbidden_customer_records),
            "warnings": len(warnings),
        })

    def collect_matching_comments(self, idea: dict[str, Any], config: FeatureConfig, warnings: list[str]) -> list[Evidence]:
        reference = idea.get("reference_num") or idea.get("id")
        if not reference:
            return []
        try:
            data = self.request_json(f"/ideas/{reference}/comments", {"page": 1, "per_page": 100})
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            warnings.append(f"Could not read comments for Aha idea {reference}: HTTP {status}.")
            return []
        except requests.RequestException as exc:
            warnings.append(f"Could not read comments for Aha idea {reference}: {exc}.")
            return []
        results: list[Evidence] = []
        for comment in data.get("comments") or []:
            text = clean_html(comment.get("body") or comment.get("text") or "")
            title = f"Comment on {idea.get('name') or reference}"
            if text_matches_feature(f"{title}\n{text}", config):
                results.append(Evidence(
                    id=f"aha-comment-{comment.get('id') or reference}", source="aha", source_type="aha_idea_comment",
                    title=title, text=text, author=display_user(comment.get("user") or comment.get("created_by")),
                    requester=requester_from_idea(idea), created_at=str(comment.get("created_at") or ""),
                    updated_at=str(comment.get("updated_at") or comment.get("created_at") or ""), url=idea_url(self.domain, idea),
                    raw_excerpt=text[:800], source_metadata={"idea_reference": reference}))
        return results

    def idea_detail_for_metadata(self, reference: str, warnings: list[str], idea: dict[str, Any]) -> dict[str, Any]:
        if not reference:
            return idea
        if opportunity_value_from_idea(idea)[0] and idea_customer_record_ids(idea):
            return idea
        try:
            data = self.request_json(f"/ideas/{reference}")
        except requests.RequestException as exc:
            warnings.append(f"Could not read Aha idea {reference} for metadata: {exc}.")
            return idea
        detail = data.get("idea") or data
        return {**idea, **detail} if isinstance(detail, dict) else idea

    def add_opportunity_value_metadata(self, item: Evidence, idea: dict[str, Any]) -> None:
        opportunity_display, opportunity_numeric = opportunity_value_from_idea(idea)
        if opportunity_display:
            item.source_metadata["opportunity_value"] = opportunity_display
        if opportunity_numeric is not None:
            item.source_metadata["opportunity_value_numeric"] = opportunity_numeric

    def collect_idea_customers(
        self,
        reference: str,
        warnings: list[str],
        idea: dict[str, Any] | None = None,
        allow_detail_fetch: bool = True,
    ) -> list[str]:
        if not reference:
            return []
        idea_payload = idea or {}
        if allow_detail_fetch and not idea_customer_record_ids(idea_payload):
            try:
                data = self.request_json(f"/ideas/{reference}")
                idea_payload = data.get("idea") or data
            except requests.RequestException as exc:
                warnings.append(f"Could not read Aha idea {reference} for customer links: {exc}.")
                idea_payload = idea or {}
        customers = self.collect_linked_idea_customers(idea_payload, warnings)
        if customers:
            return customers
        try:
            data = self.request_json(f"/ideas/{reference}/endorsements", {"page": 1, "per_page": 100})
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            if status != 404:
                warnings.append(f"Could not read customers for Aha idea {reference}: HTTP {status}.")
            return []
        except requests.RequestException as exc:
            warnings.append(f"Could not read customers for Aha idea {reference}: {exc}.")
            return []
        customers: list[str] = []
        for endorsement in data.get("idea_endorsements") or data.get("endorsements") or []:
            customer = first_display_value(
                endorsement.get("organization"),
                endorsement.get("account"),
                endorsement.get("customer"),
                endorsement.get("idea_organization"),
                endorsement.get("endorsed_by_user"),
                endorsement.get("endorsed_by_portal_user"),
                endorsement.get("endorsed_by_idea_user"),
                endorsement.get("user"),
            )
            if customer and customer not in customers:
                customers.append(customer)
        return customers

    def collect_linked_idea_customers(self, idea: dict[str, Any], warnings: list[str]) -> list[str]:
        customers: list[str] = []
        for record_id in idea_customer_record_ids(idea):
            if record_id in self.customer_record_cache:
                name = self.customer_record_cache[record_id]
                if name and name not in customers:
                    customers.append(name)
                continue
            if record_id in self.forbidden_customer_records:
                continue
            try:
                data = self.request_json(f"/custom_object_records/{record_id}")
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else "unknown"
                if status == 403:
                    self.forbidden_customer_records.add(record_id)
                    warnings.append(f"Could not read Aha Idea Customers record {record_id}: HTTP 403.")
                else:
                    warnings.append(f"Could not read Aha Idea Customers record {record_id}: HTTP {status}.")
                continue
            except requests.RequestException as exc:
                warnings.append(f"Could not read Aha Idea Customers record {record_id}: {exc}.")
                continue
            name = customer_name_from_custom_object(data.get("custom_object_record") or data)
            self.customer_record_cache[record_id] = name
            if name and name not in customers:
                customers.append(name)
        return customers

    def idea_to_evidence(self, idea: dict[str, Any]) -> Evidence:
        reference = idea.get("reference_num") or idea.get("id") or "unknown"
        text = clean_html(idea.get("description") or idea.get("body") or idea.get("name") or "")
        customers = idea_customers_from_idea(idea)
        opportunity_display, opportunity_numeric = opportunity_value_from_idea(idea)
        return Evidence(
            id=f"aha-idea-{reference}", source="aha", source_type="aha_idea", title=str(idea.get("name") or reference), text=text,
            author=display_user(idea.get("created_by") or idea.get("created_by_user") or idea.get("user")), requester=requester_from_idea(idea),
            created_at=str(idea.get("created_at") or ""), updated_at=str(idea.get("updated_at") or idea.get("created_at") or ""),
            url=idea_url(self.domain, idea), raw_excerpt=text[:800],
            source_metadata={
                "reference_num": reference,
                "workflow_status": value_name(idea.get("workflow_status")),
                "score": idea.get("score"),
                **({"opportunity_value": opportunity_display} if opportunity_display else {}),
                **({"opportunity_value_numeric": opportunity_numeric} if opportunity_numeric is not None else {}),
                **({"idea_customers": customers.split(", ")} if customers else {}),
            })


def pagination_total_pages(data: dict[str, Any]) -> int:
    pagination = data.get("pagination") or {}
    if isinstance(pagination, list) and pagination:
        pagination = pagination[0]
    try:
        return int(pagination.get("total_pages") or pagination.get("pages") or 1)
    except (TypeError, ValueError):
        return 1


def progress(message: str) -> None:
    print(message.encode("ascii", errors="replace").decode("ascii"), flush=True)


def date_range_start(date_range: str | None) -> datetime | None:
    if not date_range:
        return None
    start = date_range.split("..", 1)[0].split(",", 1)[0].strip()
    if not start:
        return None
    try:
        return datetime.fromisoformat(start.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        try:
            return datetime.fromisoformat(f"{start}T00:00:00+00:00")
        except ValueError:
            return None


def idea_created_before(idea: dict[str, Any], cutoff: datetime) -> bool:
    created_at = str(idea.get("created_at") or idea.get("updated_at") or "")
    if not created_at:
        return False
    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return False
    return created < cutoff


def clean_html(value: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", str(value or "")).split())


def display_user(user: Any) -> str:
    if isinstance(user, dict):
        return str(user.get("name") or user.get("email") or user.get("id") or "")
    return str(user or "")


def requester_from_idea(idea: dict[str, Any]) -> str:
    customer = idea_customers_from_idea(idea)
    if customer:
        return customer
    custom = idea.get("custom_fields") or {}
    if isinstance(custom, dict):
        for key in ("Idea Customers", "Account Name", "Customer", "Participant Domain", "Domain"):
            if custom.get(key):
                return stringify_customer(custom[key])
    if isinstance(custom, list):
        for field in custom:
            if not isinstance(field, dict):
                continue
            name = str(field.get("name") or field.get("key") or "")
            if name.lower() in {"idea customers", "account name", "customer", "participant domain", "domain"}:
                value = stringify_customer(field.get("value"))
                if value:
                    return value
    for key in ("requester", "customer", "organization", "account", "submitted_by", "created_by", "created_by_user"):
        value = idea.get(key)
        if isinstance(value, dict):
            name = value.get("name") or value.get("email") or value.get("domain")
            if name:
                return str(name)
        elif value:
                return str(value)
    return "Unknown"


def idea_customers_from_idea(idea: dict[str, Any]) -> str:
    for key in ("idea_customers", "ideaCustomers", "customers", "idea_customer", "ideaCustomer"):
        value = stringify_customer(idea.get(key))
        if value:
            return value
    for key in ("idea_endorsements", "endorsements"):
        value = stringify_customer(idea.get(key))
        if value:
            return value
    return ""


def idea_customer_record_ids(idea: dict[str, Any]) -> list[str]:
    record_ids: list[str] = []
    for link in idea.get("custom_object_links") or []:
        if not isinstance(link, dict):
            continue
        name = str(link.get("name") or "").lower()
        key = str(link.get("key") or "").lower()
        if name != "idea customers" and key != "customers_list":
            continue
        for record_id in link.get("record_ids") or []:
            value = str(record_id)
            if value and value not in record_ids:
                record_ids.append(value)
    return record_ids


def customer_name_from_custom_object(record: dict[str, Any]) -> str:
    for field in record.get("custom_fields") or []:
        if not isinstance(field, dict):
            continue
        key = str(field.get("key") or "").lower()
        name = str(field.get("name") or "").lower()
        if key == "customer_name" or name == "cav customer name":
            value = stringify_customer(field.get("value"))
            if value:
                return value
    return first_display_value(record)


def opportunity_value_from_idea(idea: dict[str, Any]) -> tuple[str, float | None]:
    for value in custom_field_values(idea, {"opportunity value", "opportunity_value"}):
        display = stringify_field_value(value)
        if display:
            numeric = parse_number(display)
            if numeric is not None and not has_currency_marker(display):
                display = format_currency_value(numeric)
            return display, numeric
    return "", None


def has_currency_marker(value: str) -> bool:
    return "$" in value or bool(re.search(r"\b[kmb]\b", value, flags=re.IGNORECASE))


def custom_field_values(idea: dict[str, Any], names: set[str]) -> list[Any]:
    values: list[Any] = []
    custom = idea.get("custom_fields") or {}
    if isinstance(custom, dict):
        for key, value in custom.items():
            if normalize_field_name(key) in names:
                values.append(value)
    if isinstance(custom, list):
        for field in custom:
            if not isinstance(field, dict):
                continue
            key = normalize_field_name(field.get("key") or field.get("name") or "")
            if key in names:
                values.append(field.get("value") if field.get("value") is not None else field.get("display_value"))
    return values


def normalize_field_name(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ").split())


def parse_number(value: Any) -> float | None:
    text = str(value or "")
    match = re.search(r"(-?\d[\d,]*(?:\.\d+)?)\s*([kmb])?", text, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        number = float(match.group(1).replace(",", ""))
    except ValueError:
        return None
    suffix = (match.group(2) or "").lower()
    multipliers = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}
    return number * multipliers.get(suffix, 1)


def stringify_field_value(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("display_value", "value", "name", "label", "id"):
            display = value.get(key)
            if display not in (None, ""):
                return str(display)
        return first_display_value(value)
    return stringify_customer(value)


def format_currency_value(value: float) -> str:
    if float(value).is_integer():
        return f"${int(value):,}"
    return f"${value:,.2f}"


def stringify_customer(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, list):
        names = [stringify_customer(item) for item in value]
        return ", ".join(name for name in names if name)
    if isinstance(value, dict):
        return first_display_value(
            value,
            value.get("customer"),
            value.get("account"),
            value.get("organization"),
            value.get("company"),
            value.get("endorsed_by_user"),
            value.get("user"),
        )
    return str(value)


def first_display_value(*values: Any) -> str:
    for value in values:
        if not value:
            continue
        if isinstance(value, dict):
            name = value.get("name") or value.get("company") or value.get("email") or value.get("domain") or value.get("id")
            if name:
                return str(name)
        else:
            return str(value)
    return ""


def value_name(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or value.get("value") or "")
    return str(value or "")


def idea_url(domain: str, idea: dict[str, Any]) -> str:
    url = idea.get("url") or idea.get("resource_url")
    if url:
        return str(url)
    reference = idea.get("reference_num") or idea.get("id") or ""
    return f"https://{domain}/ideas/{reference}" if domain and reference else ""
