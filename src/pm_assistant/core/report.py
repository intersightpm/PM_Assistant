from __future__ import annotations

import ast
import base64
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .config import load_feature_config

DEFAULT_REQUEST_PATTERNS = [
    r"customer feedback",
    r"customer is (?:asking|looking|trying|having|facing|requesting|using|configuring)",
    r"customers? (?:wants?|asking|looking|trying|having|facing|needs?|requested|requesting)",
    r"one of (?:my|our) customers?",
    r"customer request",
    r"would it be possible",
    r"is it possible",
    r"are there any plans",
    r"can we",
    r"could this",
    r"please consider",
    r"please include",
    r"need(?:ed)? to",
    r"we need",
    r"we want",
    r"i want",
    r"issue",
    r"problem",
    r"error",
    r"not working",
    r"unable",
    r"fails?",
]

DEFAULT_EXCLUDE_PATTERNS = [
    r"figma\.com",
    r"proposed agenda",
    r"\bkick(?:-|\s)?off\b",
    r"meeting link:",
    r"based on our discussion",
    r"please find (?:the )?(?:updates|ux mockups|mocks|mockups)",
    r"\bux screens?\b",
]

ACTIONABLE_IMPERATIVE_VERBS = (
    "add",
    "allow",
    "clarify",
    "document",
    "enable",
    "expand",
    "expose",
    "fix",
    "improve",
    "include",
    "make",
    "provide",
    "publish",
    "support",
    "update",
)

GENERIC_ACTIONABLE_ASK_PATTERNS = [
    r"^Address API feedback:",
    r"^Feature ask:",
    r"^General .+ Enhancement\.?$",
    r"^General .+ capability or usability enhancement\.?$",
    r"^Improve API support\b",
    r"^Improve API documentation\b",
    r"^(?:Document|Provide|Support|Add|Clarify|Fix|Expose|Expand) Improve API (?:support|documentation)\b",
    r"^(?:Document|Provide|Support|Add|Clarify|Fix|Expose|Expand) Close API coverage gaps\b",
    r"^Improve the accuracy, completeness, and navigability of Intersight API documentation\.?$",
    r"^Add concrete API examples and workflow recipes\.?$",
    r"^Make API object schemas, relationships, and field semantics easier to discover\.?$",
    r"^Clarify or improve API authentication, authorization, and permissions behavior\.?$",
    r"^Improve query, filtering, sorting, and pagination support or documentation\.?$",
    r"^Close API coverage gaps and expose UI capabilities through supported APIs\.?$",
    r"^Improve API support for automation and infrastructure-as-code workflows\.?$",
    r"^Improve API error messages, troubleshooting guidance, and operational diagnostics\.?$",
    r"^Improve .+ capability or usability\.?$",
]

NON_ACTIONABLE_ASK_PATTERNS = [
    r"^(thanks|thank you|yes|correct|agreed|done|fixed|resolved|works|it works|noted)\b",
    r"\bcan confirm\b",
    r"\bchecking before i reach out\b",
    r"\bcreated the theme\b",
    r"\bfor your reference\b",
    r"\bhere is the list\b",
    r"\bplease review\b",
    r"\bprovide your feedback\b",
    r"\bwe can use\b",
    r"\byou can\b",
    r"\bwe should\b",
    r"\bi think\b",
    r"\bi'?ve filed\b",
    r"\blooks like a bug\b",
    r"\broadmap\b",
    r"\bgroomed\b",
    r"\btesting\b.*\bplease ignore\b",
    r"\blow adoption\b",
    r"\bwidespread need\b",
]


def build_report_skeleton(feature_name: str, run: dict) -> str:
    """Build a full traceable Markdown draft, not just an outline."""
    config = load_feature_config(feature_name)
    return build_feature_report(feature_name, run, config.report)


def build_feature_report(feature_name: str, run: dict, profile: dict[str, Any] | None = None) -> str:
    profile = merged_report_profile(feature_name, profile)
    evidence = run.get("evidence", [])
    entries = build_entries(evidence, profile, feature_name)
    groups = story_entry_groups(entries)
    report_entries = [entry for _category, _story, rows in groups for entry in rows]
    now = generated_timestamp()
    title = profile.get("title") or f"{feature_name.title()} Feature Enhancement Feedback Report"
    source_summary = source_label_text(evidence, report_entries)

    lines = [
        f"# {title}",
        "",
        f"Generated on: {now}",
        f"Source: {source_summary}",
    ]
    lines.extend(["", "## Summary Table", ""])
    lines.extend([
        "| # | Category | User story | Customers / requesters | Distinct customers / people | Opportunity Value Total |",
        "|---:|---|---|---|---:|---:|",
    ])

    row_number = 1
    for category, story, rows in groups:
        requesters = distinct_requesters(rows)
        story_link = f"[{story}](#{story_anchor(category, story)})"
        lines.append(
            f"| {row_number} | {markdown_cell(category)} | {markdown_cell(story_link)} | "
            f"{markdown_cell(join_display_names(requesters))} | {len(requesters)} | "
            f"{category_opportunity_value_display(rows)} |"
        )
        row_number += 1

    category_descriptions = category_description_lookup(profile)
    for category, story, rows in groups:
        lines.extend([
            "",
            f'<a id="{story_anchor(category, story)}"></a>',
            f"## {category}",
            "",
            story,
            "",
            category_descriptions.get(category, ""),
            "",
            "| Customer / requester | Ask | Evidence | Opportunity Value |",
            "|---|---|---|---:|",
        ])
        for entry in sorted(rows, key=lambda row: (row["requester"].lower(), actionable_ask(row).lower(), row["created_at"])):
            lines.append(
                f"| {markdown_cell(entry['requester'])} | {markdown_cell(actionable_ask(entry))} | "
                f"{markdown_evidence_link(entry)} | {entry_opportunity_value_display(entry)} |"
            )
    if not groups:
        lines.extend([
            "",
            "## No Reportable Feedback Found",
            "",
            "The run completed, but no evidence passed the request-like feedback filters. Review the feature aliases, related terms, source filters, and raw evidence.",
        ])
    return "\n".join(lines).rstrip() + "\n"


def build_report_html(feature_name: str, run: dict) -> str:
    config = load_feature_config(feature_name)
    profile = merged_report_profile(feature_name, config.report)
    evidence = run.get("evidence", [])
    entries = build_entries(evidence, profile, feature_name)
    groups = story_entry_groups(entries)
    report_entries = [entry for _category, _story, rows in groups for entry in rows]
    now = generated_timestamp()
    title = profile.get("title") or f"{feature_name.title()} Feature Enhancement Feedback Report"
    source_summary = source_label_text(evidence, report_entries)

    parts = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '  <meta charset="utf-8">',
        f"  <title>{escape(title)}</title>",
        "  <style>",
        "    body { font-family: Segoe UI, Arial, sans-serif; line-height: 1.45; margin: 32px; max-width: 1200px; }",
        "    table { border-collapse: collapse; width: 100%; margin: 16px 0 28px; }",
        "    th, td { border: 1px solid #d0d7de; padding: 6px 8px; vertical-align: top; }",
        "    th { background: #f6f8fa; text-align: left; }",
        "    td.num, th.num { text-align: right; white-space: nowrap; }",
        "    pre { background: #f6f8fa; border: 1px solid #d0d7de; padding: 12px; white-space: pre-wrap; }",
        "    code { background: #f6f8fa; padding: 1px 4px; }",
        "    .source { color: #444; }",
        "    .back-to-summary { position: fixed; right: 24px; bottom: 24px; background: #0969da; color: #fff; padding: 8px 10px; border-radius: 4px; text-decoration: none; box-shadow: 0 2px 8px rgba(0,0,0,.18); }",
        "    .back-to-summary:hover { background: #0757b7; }",
        "  </style>",
        "</head>",
        "<body>",
        '<a class="back-to-summary" href="#summary">Back to summary</a>',
        f"<h1>{escape(title)}</h1>",
        f"<p>Generated on: {escape(now)}</p>",
        f"<p>Source: {escape(source_summary)}</p>",
    ]
    parts.extend([
        '<h2 id="summary">Summary Table</h2>',
        "<table>",
        "<thead><tr><th class=\"num\">#</th><th>Category</th><th>User story</th><th>Customers / requesters</th><th class=\"num\">Distinct customers / people</th><th class=\"num\">Opportunity Value Total</th></tr></thead>",
        "<tbody>",
    ])

    row_number = 1
    for category, story, rows in groups:
        requesters = distinct_requesters(rows)
        parts.append(
            "<tr>"
            f"<td class=\"num\">{row_number}</td>"
            f"<td>{escape(category)}</td>"
            f"<td><a href=\"#{escape(story_anchor(category, story))}\">{escape(story)}</a></td>"
            f"<td>{escape(join_display_names(requesters))}</td>"
            f"<td class=\"num\">{len(requesters)}</td>"
            f"<td class=\"num\">{escape(category_opportunity_value_display(rows))}</td>"
            "</tr>"
        )
        row_number += 1
    parts.extend(["</tbody>", "</table>"])

    category_descriptions = category_description_lookup(profile)
    for category, story, rows in groups:
        parts.extend([
            f"<h2 id=\"{escape(story_anchor(category, story))}\">{escape(category)}</h2>",
            f"<p>{escape(story)}</p>",
            f"<p>{escape(category_descriptions.get(category, ''))}</p>",
            "<table>",
            "<thead><tr><th>Customer / requester</th><th>Ask</th><th>Evidence</th><th class=\"num\">Opportunity Value</th></tr></thead>",
            "<tbody>",
        ])
        for entry in sorted(rows, key=lambda row: (row["requester"].lower(), actionable_ask(row).lower(), row["created_at"])):
            parts.append(
                "<tr>"
                f"<td>{escape(entry['requester'])}</td>"
                f"<td>{escape(actionable_ask(entry))}</td>"
                f"<td>{html_evidence_link(entry)}</td>"
                f"<td class=\"num\">{escape(entry_opportunity_value_display(entry))}</td>"
                "</tr>"
            )
        parts.extend(["</tbody>", "</table>"])

    if not groups:
        parts.extend([
            "<h2>No Reportable Feedback Found</h2>",
            "<p>The run completed, but no evidence passed the request-like feedback filters. Review the feature aliases, related terms, source filters, and raw evidence.</p>",
        ])
    parts.extend(["</body>", "</html>"])
    return "\n".join(parts) + "\n"


def write_report_files(feature_name: str, run: dict, markdown_path: Path) -> dict[str, Path]:
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    html_path = markdown_path.with_suffix(".html")
    markdown_path.write_text(build_report_skeleton(feature_name, run), encoding="utf-8", newline="\n")
    html_path.write_text(build_report_html(feature_name, run), encoding="utf-8", newline="\n")
    return {"markdown": markdown_path, "html": html_path}


def source_label_text(evidence: list[dict[str, Any]], entries: list[dict[str, Any]]) -> str:
    source_counts: defaultdict[str, int] = defaultdict(int)
    aha_idea_count = 0
    aha_comment_count = 0
    for item in evidence:
        source = str(item.get("source") or "unknown").lower()
        source_counts[source] += 1
        if source == "aha":
            source_type = item.get("source_type")
            if source_type == "aha_idea":
                aha_idea_count += 1
            elif source_type == "aha_idea_comment":
                aha_comment_count += 1

    return (
        f"matching evidence: {source_counts['webex']} Webex, {source_counts['aha']} Aha "
        f"({aha_idea_count} ideas, {aha_comment_count} comments); "
        f"{len(entries)} report entries after filtering likely asks and deduplicating exact repeats"
    )


def generated_timestamp() -> str:
    now_utc = datetime.now(timezone.utc)
    pacific = pacific_timezone(now_utc.year)
    return now_utc.astimezone(pacific).strftime("%Y-%m-%d %H:%M %Z")


def pacific_timezone(year: int) -> timezone:
    now = datetime.now(timezone.utc)
    dst_start = nth_weekday(year, 3, 6, 2).replace(hour=10, tzinfo=timezone.utc)
    dst_end = nth_weekday(year, 11, 6, 1).replace(hour=9, tzinfo=timezone.utc)
    if dst_start <= now < dst_end:
        return timezone(timedelta(hours=-7), "PDT")
    return timezone(timedelta(hours=-8), "PST")


def nth_weekday(year: int, month: int, weekday: int, n: int) -> datetime:
    first = datetime(year, month, 1)
    days_until = (weekday - first.weekday()) % 7
    return first + timedelta(days=days_until + (n - 1) * 7)


def build_entries(evidence: list[dict[str, Any]], profile: dict[str, Any], feature_name: str) -> list[dict[str, Any]]:
    entries_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for item in evidence:
        if item.get("source") == "aha" and item.get("source_type") == "aha_idea_comment":
            continue
        raw_text = clean_text(item.get("text") or item.get("raw_excerpt") or "")
        raw = extract_feedback_text(raw_text)
        if len(raw) < 20 or not is_feature_relevant(f"{item.get('title') or ''} {raw_text} {raw}", profile):
            continue
        if not is_request_like(f"{raw_text} {raw}", profile):
            continue
        category, secondary = choose_category(raw, profile, feature_name)
        story = choose_story(category, raw, profile, feature_name)
        ask = build_actionable_ask(raw, category, feature_name)
        if not ask:
            continue
        requester = extract_requester(item, raw_text)
        key = (category, normalized_feedback_key(raw))
        metadata = item.get("source_metadata") or {}
        entry = {
            "category": category,
            "user_story": story,
            "requester": requester,
            "summary": summarize(category, raw, secondary, profile, feature_name),
            "actionable_ask": ask,
            "raw_feedback": raw,
            "source_label": source_label(item),
            "created_at": item.get("created_at") or "",
            "author": item.get("author") or "",
            "url": item.get("url") or "",
            "url_label": url_label(item),
            "space_link": metadata.get("space_link") or "",
            "search_hint": search_hint(raw),
            "source": item.get("source") or "",
            "source_type": item.get("source_type") or "",
            "source_metadata": metadata,
            "opportunity_value": metadata.get("opportunity_value") or "",
            "opportunity_value_numeric": metadata.get("opportunity_value_numeric"),
        }
        current = entries_by_key.get(key)
        if current is None or entry_quality(entry) > entry_quality(current):
            entries_by_key[key] = entry
    return list(entries_by_key.values())


def report_groups(entries: list[dict[str, Any]]) -> list[tuple[str, list[tuple[str, list[dict[str, Any]]]]]]:
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_story: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        by_category[entry["category"]].append(entry)
        by_story[(entry["category"], entry["user_story"])].append(entry)
    groups = []
    for category in sorted(by_category, key=str.lower):
        stories = []
        for story in sorted({entry["user_story"] for entry in by_category[category]}, key=str.lower):
            stories.append((story, by_story[(category, story)]))
        groups.append((category, stories))
    return groups


def category_entry_groups(entries: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        if not actionable_ask(entry):
            continue
        by_category[entry["category"]].append(entry)
    return [(category, by_category[category]) for category in sorted(by_category, key=str.lower)]


def story_entry_groups(entries: list[dict[str, Any]]) -> list[tuple[str, str, list[dict[str, Any]]]]:
    by_story: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        if not actionable_ask(entry):
            continue
        category = clean_text(entry.get("category") or "")
        story = clean_text(entry.get("user_story") or "")
        if not category or not story:
            continue
        by_story[(category, story)].append(entry)
    return [
        (category, story, by_story[(category, story)])
        for category, story in sorted(by_story, key=lambda item: (item[0].lower(), item[1].lower()))
    ]


def distinct_requesters(rows: list[dict[str, Any]]) -> list[str]:
    requesters = {}
    for row in rows:
        requester = clean_text(row.get("requester") or "Unknown")
        key = requester.lower()
        if key and key not in requesters:
            requesters[key] = requester
    return sorted(requesters.values(), key=str.lower)


def join_display_names(names: list[str], limit: int = 8) -> str:
    if len(names) > limit:
        return f"{', '.join(names[:limit])}, and {len(names) - limit} more"
    return ", ".join(names)


def category_user_story(category: str, rows: list[dict[str, Any]], profile: dict[str, Any], feature_name: str) -> str:
    for configured in profile.get("categories") or []:
        if configured.get("name") != category:
            continue
        stories = configured.get("stories") or []
        for story in stories:
            if story.get("text"):
                return story["text"]
    stories = sorted({row.get("user_story") or "" for row in rows if row.get("user_story")}, key=str.lower)
    return stories[0] if stories else f"As an admin, I want {feature_name} enhancements that improve operational usefulness."


def actionable_ask(entry: dict[str, Any]) -> str:
    ask = clean_text(entry.get("actionable_ask") or "")
    if is_generic_actionable_ask(ask):
        return ""
    return ask


def build_actionable_ask(text: str, category: str, feature_name: str) -> str:
    feedback = ask_source_text(text)
    if not feedback or is_non_actionable_feedback(feedback):
        return ""

    candidate = select_request_sentence(feedback)
    if not candidate:
        return ""

    candidate = strip_request_leadin(candidate)
    if not candidate:
        return ""

    candidate = rewrite_common_actionable_ask(candidate)
    if not candidate:
        return ""

    ask = normalize_actionable_sentence(candidate, category, feature_name)
    ask = trim_actionable_ask(ask)
    if is_generic_actionable_ask(ask) or is_malformed_actionable_ask(ask):
        return ""
    return ask


def ask_source_text(text: str) -> str:
    result = clean_text(text)
    result = re.sub(r"^New feedback was posted:\s*", "", result, flags=re.IGNORECASE)
    result = re.sub(r"\b(?:Jira Id|FullStory URL|Tags|Source):\s+.*$", "", result, flags=re.IGNORECASE)
    result = re.sub(r"^(?:hi|hello|hey)(?:\s+team|\s+all|\s+\w+)?[,!:\s]+", "", result, flags=re.IGNORECASE)
    result = re.sub(r"^\(?customer feedback\s*\)\s*", "", result, flags=re.IGNORECASE)
    return clean_text(result)


def is_non_actionable_feedback(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in NON_ACTIONABLE_ASK_PATTERNS)


def select_request_sentence(text: str) -> str:
    candidates = request_candidates(text)
    if not candidates:
        return ""
    candidates.sort(key=lambda candidate: request_candidate_score(candidate), reverse=True)
    return candidates[0]


def request_candidates(text: str) -> list[str]:
    normalized = clean_text(text)
    candidates: list[str] = []
    candidates.extend(quoted_blocks(text))
    candidates.extend(split_sentences(normalized))
    tail_match = re.search(r"\b(?:request (?:coming|is)|need support for|needs? support for)\b.*$", normalized, flags=re.IGNORECASE)
    if tail_match:
        candidates.append(tail_match.group(0))
    return [candidate for candidate in unique_list([clean_text(candidate) for candidate in candidates]) if candidate]


def quoted_blocks(text: str) -> list[str]:
    return [
        clean_text(match.group(1))
        for match in re.finditer(r'"([^"]{40,})"', str(text or ""), flags=re.DOTALL)
        if clean_text(match.group(1))
    ]


def request_candidate_score(text: str) -> int:
    candidate = clean_text(text)
    lowered = candidate.lower()
    score = 0
    strong_patterns = [
        r"\bneed support for\b",
        r"\brequest is to\b",
        r"\bcustomer is unable to\b",
        r"\bcustomer needs?\b",
        r"\bintended integration should\b",
        r"\bwould it be possible\b",
        r"\bplease (?:add|include|consider|provide|document|fix|clarify|support|allow)\b",
        r"\bnot reach their proxy\b",
        r"\bconnection to host timed out\b",
    ]
    medium_patterns = [
        r"\b(?:need|needs|want|wants|request|requested|requesting)\b",
        r"\bshould support\b",
        r"\bsupport for\b",
        r"\bmissing\b",
        r"\bincomplete\b",
        r"\bunclear\b",
        r"\bconfusing\b",
        r"\bnot (?:available|exposed|working|documented)\b",
        r"\bunable\b",
        r"\bfails?\b",
        r"\berror\b",
    ]
    weak_patterns = [r"\bissue\b", r"\bproblem\b", r"\bdocumentation\b", r"\bdocs?\b"]
    score += 20 * sum(1 for pattern in strong_patterns if re.search(pattern, lowered, flags=re.IGNORECASE))
    score += 7 * sum(1 for pattern in medium_patterns if re.search(pattern, lowered, flags=re.IGNORECASE))
    score += 2 * sum(1 for pattern in weak_patterns if re.search(pattern, lowered, flags=re.IGNORECASE))
    if len(candidate) > 120:
        score += 8
    if len(candidate) > 300:
        score += 8
    if candidate_is_weak_leadin(candidate):
        score -= 30
    if is_non_actionable_feedback(candidate):
        score -= 50
    return score


def candidate_is_weak_leadin(text: str) -> bool:
    return bool(re.search(r"\bwe have customer issue with\b", text, flags=re.IGNORECASE))


def split_sentences(text: str) -> list[str]:
    normalized = clean_text(text)
    if not normalized:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", normalized)
    return [sentence.strip(" -;:") for sentence in sentences if sentence.strip(" -;:")]


def strip_request_leadin(text: str) -> str:
    result = clean_text(text).strip(" -;:")
    leadin_patterns = [
        r"^New feedback was posted:\s*",
        r"^Description:\s*",
        r"^(?:one of (?:my|our) )?customers?\s+(?:is|are|was|were)?\s*(?:asking|looking|trying|having|facing|requesting|using|configuring|needs?|wants?|requested|would like)\s+(?:for|to know if|to know whether|if|whether|about|to)?\s*",
        r"^(?:one of (?:my|our) )?customers?\s+(?:reports?|has|have|is having|are having)\s+(?:an? )?(?:issue|problem)(?:\s+where|:)?\s*",
        r"^(?:the )?customer request(?:s|ed)?\s+(?:is|was)?\s*(?:for|to)?\s*",
        r"^(?:users?|admins?|operators?|partners?)\s+(?:are|were|need|needs|want|wants|asked|asking|requested|requesting|would like)\s+(?:for|to)?\s*",
        r"^(?:we|i)\s+(?:need|want|would like)\s+(?:to|for)?\s*",
        r"^would it be possible\s+(?:to|for)?\s*",
        r"^is it possible\s+(?:to|for)?\s*",
        r"^can we\s+",
        r"^could (?:this|we|you)\s+",
        r"^please\s+",
        r"^request:\s*",
        r"^need(?:ed)?\s+(?:to|for)?\s*",
    ]
    changed = True
    while changed:
        changed = False
        for pattern in leadin_patterns:
            updated = re.sub(pattern, "", result, flags=re.IGNORECASE).strip(" -;:")
            if updated != result:
                result = updated
                changed = True
    result = re.sub(r"^(?:add|include|provide|support|allow|document|clarify|fix|expose)\s+to\s+", "", result, flags=re.IGNORECASE)
    return clean_text(result)


def rewrite_common_actionable_ask(text: str) -> str:
    candidate = clean_text(text).strip(" -;:")
    if not candidate:
        return ""

    pagerduty_proxy_match = (
        re.search(r"\bpagerduty\b", candidate, flags=re.IGNORECASE)
        and re.search(r"\b(?:cva|virtual appliance|intersight va)\b", candidate, flags=re.IGNORECASE)
        and re.search(r"\b(?:proxy|firewall|connection to host timed out|timed out)\b", candidate, flags=re.IGNORECASE)
    )
    if pagerduty_proxy_match:
        return "Support proxy configuration for CVA webhooks so Intersight can send PagerDuty notifications through the customer enterprise proxy"

    support_tail = re.search(r"\bneed support for\s+(.+)$", candidate, flags=re.IGNORECASE)
    if support_tail:
        return f"Support {clean_text(support_tail.group(1)).strip(' .')}"

    request_tail = re.search(r"\brequest is to\s+(.+)$", candidate, flags=re.IGNORECASE)
    if request_tail:
        return clean_text(request_tail.group(1)).strip(" .")

    candidate = re.sub(
        r"^consider\s+adding\s+(?:a\s+)?feature(?:\s+in\s+\w+)?\s+that\s+allows\s+(?:administrators|admins|users|customers)\s+to:?\s*",
        "",
        candidate,
        flags=re.IGNORECASE,
    )
    candidate = re.sub(
        r"^add(?:ing)?\s+(?:a\s+)?feature(?:\s+in\s+\w+)?\s+that\s+allows\s+(?:administrators|admins|users|customers)\s+to:?\s*",
        "",
        candidate,
        flags=re.IGNORECASE,
    )

    backup_match = re.search(
        r"receive\s+automated\s+email\s+notifications?\s+after\s+each\s+scheduled\s+backup",
        candidate,
        flags=re.IGNORECASE,
    )
    if backup_match:
        return "Add automated email notifications after each scheduled backup"

    webhook_event_match = re.search(
        r"(?:possible\s+to\s+)?use\s+(?:a\s+)?webhooks?\s+to\s+be\s+notified\s+on\s+(.+)$",
        candidate,
        flags=re.IGNORECASE,
    )
    if webhook_event_match:
        events = readable_event_list(webhook_event_match.group(1))
        return f"Add webhook notifications for {events} events" if events else ""

    auth_error_match = re.search(
        r"webhooks?\s+on\s+(.+?)\s+(?:and\s+(?:it'?s|it\s+is)\s+|(?:is|are)\s+)?throwing\s+401\s+authentication\s+errors?",
        candidate,
        flags=re.IGNORECASE,
    )
    if auth_error_match:
        target = clean_text(auth_error_match.group(1)).strip(" .")
        return f"Fix 401 authentication errors for webhooks on {target}" if target else ""

    disconnect_match = re.search(
        r"monitor\s+our\s+intersight[-\s]+managed\s+devices\s+with\s+(?:these\s+)?webhooks?,?\s+and\s+the\s+disconnects?\s+are\s+an\s+issue",
        candidate,
        flags=re.IGNORECASE,
    )
    if disconnect_match:
        return "Improve webhook connection reliability for monitoring Intersight-managed devices"

    if re.search(r"\bdisconnects?\s+are\s+an\s+issue\b", candidate, flags=re.IGNORECASE) and re.search(r"\bwebhooks?\b", candidate, flags=re.IGNORECASE):
        return "Improve webhook connection reliability"

    candidate = re.sub(r"^possible\s+to\s+", "", candidate, flags=re.IGNORECASE)
    candidate = re.sub(r"^consider\s+adding\s+", "add ", candidate, flags=re.IGNORECASE)
    candidate = re.sub(r"^consider\s+", "", candidate, flags=re.IGNORECASE)
    return clean_text(candidate)


def readable_event_list(text: str) -> str:
    value = clean_text(text).strip(" .")
    value = re.sub(r"\s+events?$", "", value, flags=re.IGNORECASE)
    parts = [part.strip(" ,") for part in re.split(r"\s*/\s*|,\s*", value) if part.strip(" ,")]
    if len(parts) > 1:
        prefix_words = parts[0].split()
        if len(prefix_words) > 1:
            prefix = " ".join(prefix_words[:-1])
            normalized = [parts[0]]
            for part in parts[1:]:
                normalized.append(part if " " in part else f"{prefix} {part}")
            parts = normalized
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return f"{', '.join(parts[:-1])}, and {parts[-1]}"


def normalize_actionable_sentence(text: str, category: str, feature_name: str) -> str:
    candidate = clean_text(text).strip(" -;:")
    if not candidate:
        return ""
    lowered = candidate.lower()
    if lowered.startswith(ACTIONABLE_IMPERATIVE_VERBS):
        return sentence_case(candidate)

    if re.search(r"\b(?:unable|not working|fails?|error|blank page|broken)\b", lowered):
        return sentence_case(f"Fix {candidate}")
    if re.search(r"\b(?:not exposed|not available|missing endpoint|coverage gap)\b", lowered):
        return sentence_case(f"Expose {candidate}")
    if re.search(r"\b(?:missing|incomplete|unclear|confusing|not documented)\b", lowered):
        return sentence_case(f"Document {candidate}")
    if re.search(r"\b(?:docs?|documentation|api reference|developer portal|openapi|swagger)\b", lowered) and "beyond" in lowered:
        return sentence_case(f"Expand {candidate}")
    if re.search(r"\b(?:docs?|documentation|api reference|developer portal|openapi|swagger)\b", lowered):
        return sentence_case(f"Document {candidate}")
    if "payload" in category.lower() and re.search(r"\b(?:payload|json|field|fields|object)\b", lowered):
        return sentence_case(f"Include {candidate}")
    if re.search(r"\b(?:example|sample|recipe|script)\b", lowered):
        return sentence_case(f"Provide {candidate}")
    if re.search(r"\b(?:field|fields|attribute|schema|moid|object model|relationship|wwpn)\b", lowered):
        return sentence_case(f"Expose {candidate}")
    if re.search(r"\bsupport\b", lowered):
        return sentence_case(f"Add {candidate}")
    if re.search(r"\b(?:support|integration|integrate|receiver|teams|servicenow|splunk|pagerduty)\b", lowered):
        return sentence_case(f"Support {candidate}")
    if re.search(r"\b(?:allow|configure|configurable|filter|query|odata|sort|pagination)\b", lowered):
        return sentence_case(f"Allow {candidate}")

    verb = category_action_verb(category, feature_name)
    return sentence_case(f"{verb} {candidate}")


def category_action_verb(category: str, feature_name: str) -> str:
    lowered = f"{category} {feature_name}".lower()
    if any(token in lowered for token in ("documentation", "docs", "examples", "samples", "recipes")):
        return "Provide"
    if "webhook" in lowered and "coverage" in lowered:
        return "Support"
    if any(token in lowered for token in ("schema", "object model", "field", "coverage", "endpoint", "redfish", "cimc", "ucsm")):
        return "Expose"
    if any(token in lowered for token in ("error", "debug", "reliability", "recovery")):
        return "Fix"
    if any(token in lowered for token in ("authentication", "authorization", "access", "query", "filter", "pagination")):
        return "Clarify"
    if any(token in lowered for token in ("payload", "object context")):
        return "Include"
    if any(token in lowered for token in ("automation", "sdk", "infrastructure")):
        return "Provide"
    return "Support"


def sentence_case(text: str) -> str:
    value = clean_text(text).strip(" .")
    if not value:
        return ""
    return value[:1].upper() + value[1:]


def trim_actionable_ask(text: str, max_chars: int = 280) -> str:
    ask = clean_text(text).strip(" .")
    if len(ask) > max_chars:
        truncated = ask[:max_chars].rsplit(" ", 1)[0].rstrip(",;:")
        ask = f"{truncated}..."
    if ask and not ask.endswith(("?", "!")):
        ask += "."
    return ask


def is_generic_actionable_ask(text: str) -> bool:
    ask = clean_text(text)
    if not ask:
        return True
    if len([token for token in re.findall(r"[A-Za-z0-9]+", ask) if len(token) > 2]) < 4:
        return True
    if any(re.search(pattern, ask, flags=re.IGNORECASE) for pattern in GENERIC_ACTIONABLE_ASK_PATTERNS):
        return True
    if re.fullmatch(
        r"(?:Improve|Enhance|Support|Provide|Add|Clarify|Fix|Expose) (?:the )?(?:api|apis|webhook|webhooks|feature|capability|documentation|support|functionality)\.?",
        ask,
        flags=re.IGNORECASE,
    ):
        return True
    return False


def is_malformed_actionable_ask(text: str) -> bool:
    ask = clean_text(text)
    malformed_patterns = [
        r"^Support\s+consider\b",
        r"^Support\s+possible\s+to\b",
        r"^Fix\s+monitor\b",
        r"^Fix\s+Webhooks?\s+on\b",
    ]
    return any(re.search(pattern, ask, flags=re.IGNORECASE) for pattern in malformed_patterns)


def markdown_cell(value: Any) -> str:
    return clean_text(value).replace("|", "\\|")


def markdown_evidence_link(entry: dict[str, Any]) -> str:
    label = display_source_name(entry)
    link = original_source_link(entry)
    if not link:
        return "Not available"
    attrs = evidence_link_attrs(entry)
    return f'<a href="{link}"{attrs}>{label}</a>'


def html_evidence_link(entry: dict[str, Any]) -> str:
    label = escape(display_source_name(entry))
    link = original_source_link(entry)
    if not link:
        return "Not available"
    attrs = evidence_link_attrs(entry)
    return f'<a href="{escape(link, quote=True)}"{attrs}>{label}</a>'


def evidence_link_attrs(entry: dict[str, Any]) -> str:
    if str(entry.get("source") or "").lower() == "webex":
        return ""
    return ' target="_blank" rel="noopener noreferrer"'


def entry_opportunity_value_display(entry: dict[str, Any]) -> str:
    if str(entry.get("source") or "").lower() != "aha":
        return "Not available"
    return clean_text(entry.get("opportunity_value") or "Not available")


def category_opportunity_value_display(rows: list[dict[str, Any]]) -> str:
    total = 0.0
    has_value = False
    explicit_zero = False
    for row in rows:
        if str(row.get("source") or "").lower() != "aha":
            continue
        value = row.get("opportunity_value_numeric")
        if isinstance(value, (int, float)):
            has_value = True
            explicit_zero = explicit_zero or float(value) == 0
            total += float(value)
    if total:
        return format_opportunity_value(total)
    if explicit_zero:
        return "$0"
    return "Not available" if not has_value else "$0"


def story_section_lookup(groups: list[tuple[str, list[tuple[str, list[dict[str, Any]]]]]]) -> dict[tuple[str, str], str]:
    story_sections: dict[tuple[str, str], str] = {}
    story_number = 1
    for category, stories in groups:
        for story, _rows in stories:
            story_sections[(category, story)] = f"Story {story_number:02d}"
            story_number += 1
    return story_sections


def story_feature_ask(rows: list[dict[str, Any]]) -> str:
    summaries = sorted({entry["summary"] for entry in rows}, key=str.lower)
    return summaries[0] if summaries else ""


def story_opportunity_value(rows: list[dict[str, Any]]) -> float | None:
    values = []
    for entry in rows:
        value = entry.get("opportunity_value_numeric")
        if isinstance(value, (int, float)):
            values.append(float(value))
    return sum(values) if values else None


def format_opportunity_value(value: float | None) -> str:
    if value is None:
        return "Not available"
    if float(value).is_integer():
        return f"${int(value):,}"
    return f"${value:,.2f}"


def entry_quality(entry: dict[str, Any]) -> tuple[int, int, int, str]:
    requester = str(entry.get("requester") or "")
    clear_requester = int(bool(requester and requester.lower() != "unknown" and "@" not in requester))
    has_idea_customers = int(bool((entry.get("source_metadata") or {}).get("idea_customers")))
    raw_length = len(str(entry.get("raw_feedback") or ""))
    source_rank = {"webex": 2, "aha": 1}.get(str(entry.get("source") or "").lower(), 0)
    return (has_idea_customers, clear_requester, raw_length, source_rank, str(entry.get("created_at") or ""))


def merged_report_profile(feature_name: str, profile: dict[str, Any] | None) -> dict[str, Any]:
    config = load_feature_config(feature_name)
    merged = dict(config.report or {})
    merged.update(profile or {})
    merged.setdefault("category_hints", config.category_hints)
    merged.setdefault("feature_anchor_terms", config.anchor_terms())
    merged.setdefault("require_feature_anchor", not config.related_terms_match_without_feature)
    merged["categories"] = normalized_report_categories(merged, config.category_hints)
    return merged


def normalized_report_categories(profile: dict[str, Any], category_hints: list[str]) -> list[dict[str, Any]]:
    configured = [category for category in profile.get("categories") or [] if isinstance(category, dict)]
    hinted: dict[str, dict[str, Any]] = {hint: {"name": hint, "description": "", "patterns": [], "summaries": [], "stories": []} for hint in category_hints}
    extras: list[dict[str, Any]] = []
    for category in configured:
        hint = best_category_hint(str(category.get("name") or ""), category_hints)
        if hint:
            merge_category(hinted[hint], category)
        else:
            extras.append(category)
    return [category for category in hinted.values() if category_has_rules(category)] + extras


def best_category_hint(category_name: str, category_hints: list[str]) -> str:
    normalized_name = normalize_category_name(category_name)
    if not normalized_name:
        return ""
    best_hint = ""
    best_score = 0
    name_tokens = category_tokens(category_name)
    for hint in category_hints:
        normalized_hint = normalize_category_name(hint)
        if normalized_name == normalized_hint:
            return hint
        if normalized_name in normalized_hint or normalized_hint in normalized_name:
            return hint
        overlap = len(name_tokens & category_tokens(hint))
        if overlap > best_score:
            best_hint = hint
            best_score = overlap
    return best_hint if best_score >= 2 else ""


def merge_category(target: dict[str, Any], source: dict[str, Any]) -> None:
    descriptions = [str(value).strip() for value in (target.get("description"), source.get("description")) if str(value or "").strip()]
    target["description"] = " ".join(dict.fromkeys(descriptions))
    target["patterns"] = unique_list([*(target.get("patterns") or []), *(source.get("patterns") or [])])
    target["summaries"] = [*(target.get("summaries") or []), *(source.get("summaries") or [])]
    if source.get("summary"):
        target["summary"] = target.get("summary") or source.get("summary")
    target["stories"] = [*(target.get("stories") or []), *(source.get("stories") or [])]


def category_has_rules(category: dict[str, Any]) -> bool:
    return bool(category.get("patterns") or category.get("summaries") or category.get("stories") or category.get("description"))


def normalize_category_name(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


def category_tokens(value: str) -> set[str]:
    ignored = {"and", "or", "the", "a", "an", "of", "for", "to", "with"}
    return {token for token in normalize_category_name(value).split() if token not in ignored}


def unique_list(values: list[Any]) -> list[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for value in values:
        key = str(value)
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def is_feature_relevant(text: str, profile: dict[str, Any]) -> bool:
    if not profile.get("require_feature_anchor", True):
        return True
    lowered = clean_text(text).lower()
    anchors = [" ".join(str(term).lower().split()) for term in profile.get("feature_anchor_terms") or []]
    return any(anchor and anchor in lowered for anchor in anchors)


def normalized_feedback_key(text: str) -> str:
    normalized = clean_text(text).lower()
    normalized = re.sub(r"\b(new feedback|customer feedback|description|jira id|fullstory url|tags|source)\b", " ", normalized)
    normalized = re.sub(r"https?://\S+", " ", normalized)
    return re.sub(r"\W+", "", normalized)[:240]


def is_request_like(text: str, profile: dict[str, Any]) -> bool:
    lowered = text.lower()
    exclude_patterns = string_patterns(profile.get("exclude_patterns") or DEFAULT_EXCLUDE_PATTERNS)
    if any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in exclude_patterns):
        return False
    request_patterns = string_patterns(profile.get("request_patterns") or DEFAULT_REQUEST_PATTERNS)
    return any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in request_patterns)


def string_patterns(patterns: Any) -> list[str]:
    return [pattern for pattern in patterns if isinstance(pattern, str) and pattern]


def extract_field(text: str, field: str, stop_fields: list[str]) -> str | None:
    stops = "|".join(re.escape(stop) for stop in stop_fields)
    match = re.search(
        rf"{re.escape(field)}:\s*(.*?)(?=\s+(?:{stops}):|$)",
        text,
        flags=re.IGNORECASE,
    )
    return clean_text(match.group(1)) if match else None


def extract_requester(item: dict[str, Any], text: str) -> str:
    metadata = item.get("source_metadata") or {}
    idea_customers = metadata.get("idea_customers")
    if idea_customers:
        if isinstance(idea_customers, list):
            return ", ".join(str(customer) for customer in idea_customers if str(customer).strip())
        return clean_text(idea_customers)
    account = extract_field(
        text,
        "Account Name",
        ["Environment", "Type", "Open for follow-up", "Description", "Jira Id", "FullStory URL", "Tags", "Source"],
    )
    if account:
        return account
    domain = extract_field(
        text,
        "Participant Domain",
        ["Account Name", "Environment", "Type", "Description", "Jira Id"],
    )
    submitted = re.search(
        r"Submitted date\([^)]*\)\s+([^\s()]+)\s+\(customer feedback \)",
        text,
        flags=re.IGNORECASE,
    )
    if submitted:
        email = submitted.group(1)
        return email.split("@", 1)[1] if "@" in email else email
    if domain:
        return domain
    return clean_text(item.get("requester") or item.get("author") or "Unknown")


def extract_feedback_text(text: str) -> str:
    description = extract_field(text, "Description", ["Jira Id", "FullStory URL", "Tags", "Source"])
    if description:
        return description
    match = re.search(r"\(customer feedback \)\s*(.*)", text, flags=re.IGNORECASE)
    if match:
        return clean_text(match.group(1))
    return text


def choose_category(text: str, profile: dict[str, Any], feature_name: str) -> tuple[str, list[str]]:
    scores: list[tuple[str, int]] = []
    for category in profile.get("categories") or []:
        score = sum(1 for pattern in category.get("patterns", []) if re.search(pattern, text, flags=re.IGNORECASE))
        if score:
            scores.append((category["name"], score))
    if not scores:
        return profile.get("general_category") or f"General {feature_name.title()} Enhancement", []
    scores.sort(key=lambda item: item[1], reverse=True)
    return scores[0][0], [name for name, score in scores[1:4] if score > 0]


def choose_story(category: str, text: str, profile: dict[str, Any], feature_name: str) -> str:
    default_story = ""
    for configured in profile.get("categories") or []:
        if configured.get("name") != category:
            continue
        for story in configured.get("stories") or []:
            patterns = story.get("patterns", [])
            if patterns and any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns):
                return story["text"]
            if not patterns and not default_story:
                default_story = story["text"]
        break
    return default_story or f"As an admin, I want {feature_name} enhancements that improve operational usefulness."


def summarize(category: str, text: str, secondary: list[str], profile: dict[str, Any], feature_name: str) -> str:
    del secondary
    for configured in profile.get("categories") or []:
        if configured.get("name") == category:
            for summary in configured.get("summaries") or []:
                if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in summary.get("patterns", [])):
                    result = summary["text"]
                    break
            else:
                result = configured.get("summary") or f"Improve {feature_name} capability or usability."
            break
    else:
        result = f"General {feature_name} capability or usability enhancement."
    return result


def category_description_lookup(profile: dict[str, Any]) -> dict[str, str]:
    return {category["name"]: category.get("description", "") for category in profile.get("categories") or []}


def source_label(item: dict[str, Any]) -> str:
    metadata = item.get("source_metadata") or {}
    if item.get("source") == "webex":
        return metadata.get("room_title") or item.get("title") or "Webex"
    if item.get("source") == "aha":
        return item.get("title") or metadata.get("reference_num") or "Aha"
    return item.get("title") or item.get("source") or "Unknown source"


def url_label(item: dict[str, Any]) -> str:
    if item.get("source") == "webex":
        return ""
    if item.get("source") == "aha":
        return "Aha"
    return "Open source"


def markdown_source_line(entry: dict[str, Any]) -> str:
    source_name = display_source_name(entry)
    link = original_source_link(entry)
    link_text = f"[original]({link})" if link else "original unavailable"
    return ", ".join(part for part in [source_name, link_text, entry.get("created_at") or ""] if part)


def html_source_line(entry: dict[str, Any]) -> str:
    source_name = escape(display_source_name(entry))
    link = original_source_link(entry)
    link_text = (
        f'<a href="{escape(link, quote=True)}" target="_blank" rel="noopener noreferrer">original</a>'
        if link else "original unavailable"
    )
    return ", ".join(part for part in [source_name, link_text, escape(entry.get("created_at") or "")] if part)


def display_source_name(entry: dict[str, Any]) -> str:
    source = str(entry.get("source") or "").lower()
    if source == "aha":
        return "Aha"
    if source == "webex":
        return "Webex"
    return clean_text(entry.get("source_label") or entry.get("source") or "Unknown source")


def original_source_link(entry: dict[str, Any]) -> str:
    if entry.get("source") == "webex":
        return webex_app_message_link(entry) or str(entry.get("space_link") or entry.get("url") or "")
    return str(entry.get("url") or entry.get("space_link") or "")


def webex_app_message_link(entry: dict[str, Any]) -> str:
    metadata = entry.get("source_metadata") or {}
    room_id = decoded_webex_resource_id(metadata.get("room_id"))
    message_id = decoded_webex_resource_id(metadata.get("message_id"))
    if not room_id:
        match = re.search(r"[?&]space=([^&]+)", str(entry.get("space_link") or ""))
        room_id = match.group(1) if match else ""
    if not room_id:
        return ""
    link = f"webexteams://im?space={quote(room_id, safe='')}"
    if message_id:
        link += f"&message={quote(message_id, safe='')}"
    return link


def decoded_webex_resource_id(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", raw):
        return raw
    padded = raw + "=" * (-len(raw) % 4)
    try:
        decoded = base64.b64decode(padded, validate=True).decode("utf-8")
    except Exception:
        return ""
    match = re.search(r"/(?:ROOM|MESSAGE)/([^/?#]+)$", decoded, flags=re.IGNORECASE)
    return match.group(1) if match else ""


def clean_text(text: Any) -> str:
    if isinstance(text, dict):
        for key in ("body", "text", "description", "name"):
            if text.get(key):
                return clean_text(text[key])
    if isinstance(text, str) and text.strip().startswith("{") and "'body'" in text[:200]:
        try:
            parsed = ast.literal_eval(text)
        except (SyntaxError, ValueError):
            parsed = None
        if isinstance(parsed, dict):
            return clean_text(parsed)
    return " ".join(str(text or "").replace("\r", " ").replace("\n", " ").split())


def markdown_anchor(heading: str) -> str:
    anchor = heading.lower()
    anchor = re.sub(r"[^\w\s-]", "", anchor)
    return re.sub(r"\s+", "-", anchor.strip())


def story_anchor(category: str, story: str) -> str:
    return markdown_anchor(f"{category} {story}")


def search_hint(text: str) -> str:
    compact = clean_text(text)
    return compact[:90] + ("..." if len(compact) > 90 else "")
