from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from pm_assistant.core.matching import text_matches_feature
from pm_assistant.core.models import Evidence, FeatureConfig

from .base import Connector, ConnectorResult

WEBEX_BASE = "https://webexapis.com/v1"
TRANSIENT_STATUSES = {429, 502, 503}


class WebexConnector(Connector):
    name = "webex"

    def configured(self) -> tuple[bool, str]:
        missing = [name for name in ("WEBEX_CLIENT_ID", "WEBEX_CLIENT_SECRET", "WEBEX_REFRESH_TOKEN", "WEBEX_REDIRECT_URI") if not os.getenv(name)]
        if missing:
            return False, f"Missing Webex environment variables: {', '.join(missing)}. Fill them in .env."
        return True, "Webex credentials are present."

    def doctor(self) -> ConnectorResult:
        ok, message = self.configured()
        if not ok:
            return ConnectorResult(warnings=[message])
        try:
            token = self.get_access_token()
            response = request_with_retries("get", f"{WEBEX_BASE}/rooms", headers={"Authorization": f"Bearer {token}"}, params={"max": 1}, timeout=30)
            response.raise_for_status()
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            return ConnectorResult(warnings=[f"Webex API check failed with HTTP {status}. Verify OAuth app, refresh token, and room access."])
        except requests.RequestException as exc:
            return ConnectorResult(warnings=[f"Webex API check failed: {exc}"])
        return ConnectorResult(warnings=["Webex API check passed."])

    def collect(self, config: FeatureConfig, date_range: str | None = None) -> ConnectorResult:
        ok, message = self.configured()
        if not ok:
            return ConnectorResult(warnings=[message])
        warnings: list[str] = []
        token = self.get_access_token()
        rooms = self.get_rooms(token)
        filters = config.source_filters or {}
        collection_profile = str(filters.get("collection_profile") or "accuracy").lower()
        room_filter_key = "webex_room_contains" if collection_profile == "fast" else "webex_accuracy_room_contains"
        max_rooms_key = "webex_max_rooms" if collection_profile == "fast" else "webex_accuracy_max_rooms"
        room_contains = [str(item).lower() for item in filters.get(room_filter_key) or []]
        excluded_rooms = [str(item).lower() for item in filters.get("webex_excluded_room_contains") or []]
        max_rooms = filters.get(max_rooms_key)
        evidence: list[Evidence] = []
        progress(f"[webex] fetched {len(rooms)} accessible rooms")
        selected = []
        for room in rooms:
            title = str(room.get("title") or "")
            if room_contains and not any(term in title.lower() for term in room_contains):
                continue
            if excluded_rooms and any(term in title.lower() for term in excluded_rooms):
                continue
            selected.append(room)
            if max_rooms and len(selected) >= int(max_rooms):
                break
        progress(f"[webex] selected {len(selected)} rooms for message scan")
        for index, room in enumerate(selected, start=1):
            try:
                progress(f"[webex] scanning room {index}/{len(selected)}: {room.get('title')}")
                evidence.extend(self.get_matching_messages(token, room, config, date_range=date_range))
            except requests.RequestException as exc:
                warnings.append(f"Could not collect Webex room {room.get('title')}: {exc}")
        return ConnectorResult(evidence=evidence, warnings=warnings, metadata={
            "collection_profile": collection_profile,
            "rooms_available": len(rooms),
            "rooms_selected": len(selected),
            "room_filter": room_contains,
            "max_rooms": max_rooms,
            "warnings": len(warnings),
        })

    def get_access_token(self) -> str:
        response = request_with_retries(
            "post",
            f"{WEBEX_BASE}/access_token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "refresh_token",
                "client_id": os.environ["WEBEX_CLIENT_ID"],
                "client_secret": os.environ["WEBEX_CLIENT_SECRET"],
                "refresh_token": os.environ["WEBEX_REFRESH_TOKEN"],
                "redirect_uri": os.environ["WEBEX_REDIRECT_URI"],
            },
            timeout=30,
        )
        response.raise_for_status()
        return str(response.json()["access_token"])

    def get_rooms(self, token: str) -> list[dict[str, Any]]:
        rooms: list[dict[str, Any]] = []
        url = f"{WEBEX_BASE}/rooms"
        params: dict[str, Any] | None = {"max": 100}
        while url:
            response = request_with_retries("get", url, headers={"Authorization": f"Bearer {token}"}, params=params, timeout=30)
            response.raise_for_status()
            rooms.extend(response.json().get("items", []))
            url = next_page_url(response)
            params = None
        return rooms

    def get_matching_messages(self, token: str, room: dict[str, Any], config: FeatureConfig, date_range: str | None = None) -> list[Evidence]:
        results: list[Evidence] = []
        room_id = str(room.get("id") or "")
        room_title = str(room.get("title") or "")
        cutoff = cutoff_for_room(room_title, config, date_range=date_range)
        url = f"{WEBEX_BASE}/messages"
        params: dict[str, Any] | None = {"roomId": room_id, "max": 100}
        while url:
            response = request_with_retries("get", url, headers={"Authorization": f"Bearer {token}"}, params=params, timeout=30)
            response.raise_for_status()
            page_messages = response.json().get("items", [])
            for message_index, message in enumerate(page_messages):
                created_at = str(message.get("created") or "")
                if cutoff and created_at:
                    created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    if created < cutoff:
                        return results
                text = message.get("text") or message.get("markdown") or ""
                if not text_matches_feature(text, config):
                    continue
                message_id = str(message.get("id") or "")
                results.append(Evidence(
                    id=f"webex-message-{message_id}", source="webex", source_type="webex_message", title=room_title, text=str(text),
                    author=str(message.get("personDisplayName") or message.get("personEmail") or ""),
                    requester=str(message.get("personEmail") or message.get("personDisplayName") or "Unknown"),
                    created_at=created_at, updated_at=created_at,
                    url=f"{WEBEX_BASE}/messages/{message_id}" if message_id else "", raw_excerpt=str(text)[:800],
                    source_metadata={
                        "room_id": room_id,
                        "room_title": room_title,
                        "space_link": f"webexteams://im?space={room_id}",
                        "message_id": message_id,
                        "parent_id": str(message.get("parentId") or ""),
                        "source_context": webex_source_context(page_messages, message_index),
                    },
                ))
            url = next_page_url(response)
            params = None
        return results


def next_page_url(response: requests.Response) -> str | None:
    for link in response.headers.get("Link", "").split(","):
        if 'rel="next"' in link:
            return link.split(";")[0].strip("<>")
    return None


def progress(message: str) -> None:
    print(message.encode("ascii", errors="replace").decode("ascii"), flush=True)


def webex_source_context(messages: list[dict[str, Any]], match_index: int, radius: int = 2) -> list[dict[str, str]]:
    if match_index < 0 or match_index >= len(messages):
        return []
    matched = messages[match_index]
    matched_parent = str(matched.get("parentId") or "")
    start = max(0, match_index - radius)
    end = min(len(messages), match_index + radius + 1)
    context: list[dict[str, str]] = []
    for index in range(start, end):
        message = messages[index]
        parent_id = str(message.get("parentId") or "")
        same_thread = bool(matched_parent and parent_id == matched_parent) or index == match_index
        context.append({
            "position": "match" if index == match_index else ("nearby_thread" if same_thread else "nearby_room"),
            "created_at": str(message.get("created") or ""),
            "author": str(message.get("personDisplayName") or message.get("personEmail") or ""),
            "message_id": str(message.get("id") or ""),
            "parent_id": parent_id,
            "text": str(message.get("text") or message.get("markdown") or "")[:2000],
        })
    return context


def request_with_retries(method: str, url: str, attempts: int = 3, **kwargs: Any) -> requests.Response:
    last_error: requests.RequestException | None = None
    for attempt in range(attempts):
        try:
            response = requests.request(method, url, **kwargs)
            if response.status_code in TRANSIENT_STATUSES and attempt < attempts - 1:
                time.sleep(retry_sleep_seconds(response, attempt))
                continue
            return response
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_error = exc
            if attempt >= attempts - 1:
                raise
            time.sleep(2 ** attempt)
    if last_error:
        raise last_error
    raise RuntimeError("request retry loop ended unexpectedly")


def retry_sleep_seconds(response: requests.Response, attempt: int) -> int:
    retry_after = response.headers.get("Retry-After")
    if retry_after and retry_after.isdigit():
        return max(1, min(30, int(retry_after)))
    return min(30, 2 ** attempt)


def cutoff_for_room(room_title: str, config: FeatureConfig, date_range: str | None = None) -> datetime | None:
    filters = config.source_filters or {}
    default_years = filters.get("webex_default_years", 1)
    extended_years = filters.get("webex_extended_years", 3)
    extended_rooms = [str(item).lower() for item in filters.get("webex_extended_room_contains") or []]
    try:
        years = int(extended_years if any(name in room_title.lower() for name in extended_rooms) else default_years)
    except (TypeError, ValueError):
        years = 1
    default_cutoff = None if years <= 0 else datetime.now(timezone.utc) - timedelta(days=365 * years)
    range_cutoff = date_range_start(date_range)
    if default_cutoff and range_cutoff:
        return max(default_cutoff, range_cutoff)
    return range_cutoff or default_cutoff


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
