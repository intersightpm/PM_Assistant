from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

from .config import load_feature_config
from .report import (
    clean_text,
    display_source_name,
    entry_opportunity_value_display,
    evidence_link_attrs,
    generated_timestamp,
    html_evidence_link,
    merged_report_profile,
    original_source_link,
)
from .storage import RUNS_DIR, load_run

REPORT_FORMATS_DIR = Path("report_formats")
DEFAULT_FORMAT_NAME = "feature_feedback"
BANNED_REPORT_TEXT = [
    "Related themes:",
    "Address API feedback:",
    "Feature ask:",
    "Recommended Product Response",
    "Exclusions Applied",
    "```",
]


@dataclass(slots=True)
class ValidationResult:
    ok: bool
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "errors": self.errors}


def report_format_path(format_name: str = DEFAULT_FORMAT_NAME) -> Path:
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "", format_name) or DEFAULT_FORMAT_NAME
    return REPORT_FORMATS_DIR / f"{safe_name}.md"


def load_report_format(format_name: str = DEFAULT_FORMAT_NAME) -> str:
    path = report_format_path(format_name)
    if not path.exists():
        raise FileNotFoundError(f"Report format '{format_name}' was not found at {path}")
    return path.read_text(encoding="utf-8")


def prepare_report_input(
    feature_name: str,
    run_id: str,
    format_name: str = DEFAULT_FORMAT_NAME,
    runs_dir: Path = RUNS_DIR,
) -> dict[str, Any]:
    run = load_run(run_id, runs_dir=runs_dir)
    package = build_report_input(feature_name, run, format_name=format_name)
    output_path = runs_dir / run_id / "report_input.json"
    output_path.write_text(json.dumps(package, indent=2), encoding="utf-8", newline="\n")
    return package


def build_report_input(feature_name: str, run: dict[str, Any], format_name: str = DEFAULT_FORMAT_NAME) -> dict[str, Any]:
    config = load_feature_config(feature_name)
    profile = merged_report_profile(feature_name, config.report)
    evidence = run.get("evidence", [])
    title = profile.get("title") or f"{feature_name.title()} Feature Enhancement Feedback Report"
    return {
        "schema_version": 2,
        "input_mode": "raw_evidence_for_codex_review",
        "format_name": format_name,
        "format_path": str(report_format_path(format_name)),
        "run_id": run.get("run_id") or "",
        "feature_name": feature_name,
        "title": title,
        "generated_on": generated_timestamp(),
        "source": raw_source_label_text(evidence),
        "feature_profile": {
            "category_hints": config.category_hints,
            "feature_anchor_terms": config.anchor_terms(),
            "categories": [
                {
                    "name": clean_text(category.get("name") or ""),
                    "description": clean_text(category.get("description") or ""),
                    "stories": [clean_text(story.get("text") or "") for story in category.get("stories") or [] if story.get("text")],
                }
                for category in profile.get("categories") or []
            ],
        },
        "review_rubric": evidence_review_rubric(),
        "evidence_items": [report_input_evidence_item(item) for item in evidence],
        "instructions": {
            "codex_writes": [
                "semantic evidence review",
                "report inclusion/exclusion decisions",
                "summary rows",
                "detail sections",
                "Ask text",
                "final report.md prose",
            ],
            "code_owns": ["raw evidence collection", "evidence links", "opportunity value extraction", "HTML rendering", "mechanical validation"],
        },
    }


def raw_source_label_text(evidence: list[dict[str, Any]]) -> str:
    source_counts: dict[str, int] = {}
    aha_idea_count = 0
    aha_comment_count = 0
    for item in evidence:
        source = str(item.get("source") or "unknown").lower()
        source_counts[source] = source_counts.get(source, 0) + 1
        if source == "aha":
            source_type = item.get("source_type")
            if source_type == "aha_idea":
                aha_idea_count += 1
            elif source_type == "aha_idea_comment":
                aha_comment_count += 1
    return (
        f"raw evidence candidates: {source_counts.get('webex', 0)} Webex, {source_counts.get('aha', 0)} Aha "
        f"({aha_idea_count} ideas, {aha_comment_count} comments). "
        "Codex reviewed candidates semantically before including report rows."
    )


def evidence_review_rubric() -> dict[str, list[str]]:
    return {
        "include_only_if": [
            "The evidence states or clearly represents a customer/requester ask, pain point, product gap, or enhancement request.",
            "The ask is about the requested feature or a configured feature category.",
            "The ask remains unmet in the provided evidence context.",
            "The report row can cite an original Webex or Aha evidence link.",
        ],
        "exclude_if": [
            "Internal team chatter, engineering discussion, roadmap debate, FYI, announcement, or marketing/news content.",
            "Meeting summaries, action-item lists, deck edits, Jira/process updates, scheduling, or project management tasks.",
            "Support answers, confirmations, workaround guidance, troubleshooting responses, or references shared only as an answer.",
            "The same context says the capability is already available, shipped, fixed, resolved, answered, no change required, or closed.",
            "The text only asks for feedback, review, prioritization, funding, or internal approval.",
        ],
        "resolution_signals": [
            "available",
            "already supported",
            "shipped",
            "released",
            "fixed",
            "resolved",
            "closed",
            "answered",
            "completed",
            "no changes required",
            "you can use",
        ],
    }


def report_input_evidence_item(item: dict[str, Any]) -> dict[str, Any]:
    entry = {
        "source": item.get("source") or "",
        "source_type": item.get("source_type") or "",
        "title": clean_text(item.get("title") or ""),
        "customer_requester": clean_text(item.get("requester") or item.get("author") or "Unknown"),
        "author": clean_text(item.get("author") or ""),
        "created_at": item.get("created_at") or "",
        "updated_at": item.get("updated_at") or "",
        "evidence_url": original_source_link(item),
        "markdown_evidence": markdown_evidence_link(item),
        "html_evidence": html_evidence_link(item),
        "opportunity_value": raw_item_opportunity_value_display(item),
        "opportunity_value_numeric": raw_item_opportunity_value_numeric(item),
        "raw_evidence": clean_text(item.get("text") or item.get("raw_excerpt") or ""),
        "raw_excerpt": clean_text(item.get("raw_excerpt") or item.get("text") or "")[:800],
        "source_metadata": item.get("source_metadata") or {},
        "candidate_reason": "Matched broad collection filters. Codex must decide whether this is reportable unresolved customer feedback.",
        "review_notes": "",
    }
    context = (item.get("source_metadata") or {}).get("source_context")
    if context:
        entry["source_context"] = context
    return entry


def raw_item_opportunity_value_display(item: dict[str, Any]) -> str:
    if str(item.get("source") or "").lower() != "aha":
        return "Not available"
    metadata = item.get("source_metadata") or {}
    return clean_text(metadata.get("opportunity_value") or "Not available")


def raw_item_opportunity_value_numeric(item: dict[str, Any]) -> Any:
    if str(item.get("source") or "").lower() != "aha":
        return None
    return (item.get("source_metadata") or {}).get("opportunity_value_numeric")


def report_input_entry(entry: dict[str, Any]) -> dict[str, Any]:
    source = str(entry.get("source") or "").lower()
    evidence_url = original_source_link(entry)
    return {
        "customer_requester": clean_text(entry.get("requester") or "Unknown"),
        "source": display_source_name(entry),
        "source_type": entry.get("source_type") or "",
        "evidence_url": evidence_url,
        "markdown_evidence": markdown_evidence_link(entry),
        "html_evidence": html_evidence_link(entry),
        "opportunity_value": entry_opportunity_value_display(entry),
        "opportunity_value_numeric": entry.get("opportunity_value_numeric") if source == "aha" else None,
        "raw_evidence": entry.get("raw_feedback") or "",
        "created_at": entry.get("created_at") or "",
        "category": entry.get("category") or "",
        "user_story": entry.get("user_story") or "",
    }


def markdown_evidence_link(entry: dict[str, Any]) -> str:
    link = original_source_link(entry)
    if not link:
        return "Not available"
    attrs = evidence_link_attrs(entry)
    return f'<a href="{link}"{attrs}>{display_source_name(entry)}</a>'


def distinct_requesters(rows: list[dict[str, Any]]) -> list[str]:
    seen: dict[str, str] = {}
    for row in rows:
        requester = clean_text(row.get("requester") or "Unknown")
        key = requester.lower()
        if key and key not in seen:
            seen[key] = requester
    return sorted(seen.values(), key=str.lower)


def distinct_requesters_text(rows: list[dict[str, Any]]) -> str:
    names = distinct_requesters(rows)
    if len(names) > 8:
        return f"{', '.join(names[:8])}, and {len(names) - 8} more"
    return ", ".join(names)


def category_description(profile: dict[str, Any], category: str) -> str:
    for configured in profile.get("categories") or []:
        if configured.get("name") == category:
            return clean_text(configured.get("description") or "")
    return ""


def load_report_input(run_id: str, runs_dir: Path = RUNS_DIR) -> dict[str, Any]:
    path = runs_dir / run_id / "report_input.json"
    if not path.exists():
        raise FileNotFoundError(f"Report input for run '{run_id}' was not found at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def render_report_html(run_id: str, markdown_path: Path | None = None, runs_dir: Path = RUNS_DIR) -> Path:
    run_dir = runs_dir / run_id
    markdown_path = markdown_path or run_dir / "report.md"
    html_path = markdown_path.with_suffix(".html")
    markdown = markdown_path.read_text(encoding="utf-8")
    html_path.write_text(markdown_to_report_html(markdown), encoding="utf-8", newline="\n")
    return html_path


def markdown_to_report_html(markdown: str) -> str:
    lines = markdown.splitlines()
    parts = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '  <meta charset="utf-8">',
        "  <title>Feature Feedback Report</title>",
        "  <style>",
        "    body { font-family: Segoe UI, Arial, sans-serif; line-height: 1.45; margin: 32px; max-width: 1200px; }",
        "    table { border-collapse: collapse; width: 100%; margin: 16px 0 28px; }",
        "    th, td { border: 1px solid #d0d7de; padding: 6px 8px; vertical-align: top; }",
        "    th { background: #f6f8fa; text-align: left; }",
        "    td.num, th.num { text-align: right; white-space: nowrap; }",
        "    .back-to-summary { position: fixed; right: 24px; bottom: 24px; background: #0969da; color: #fff; padding: 8px 10px; border-radius: 4px; text-decoration: none; box-shadow: 0 2px 8px rgba(0,0,0,.18); }",
        "    .back-to-summary:hover { background: #0757b7; }",
        "  </style>",
        "</head>",
        "<body>",
        '<a class="back-to-summary" href="#summary">Back to summary</a>',
    ]
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("# "):
            parts.append(f"<h1>{escape(line[2:].strip())}</h1>")
        elif line == "## Summary Table":
            parts.append('<h2 id="summary">Summary Table</h2>')
        elif line.startswith("## "):
            parts.append(f"<h2>{escape(line[3:].strip())}</h2>")
        elif line.startswith('<a id="'):
            parts.append(line)
        elif line.startswith("|") and index + 1 < len(lines) and lines[index + 1].startswith("|---"):
            table_lines = [line]
            index += 2
            while index < len(lines) and lines[index].startswith("|"):
                table_lines.append(lines[index])
                index += 1
            index -= 1
            parts.append(markdown_table_to_html(table_lines))
        elif line.strip():
            parts.append(f"<p>{inline_markdown_to_html(line)}</p>")
        index += 1
    parts.extend(["</body>", "</html>"])
    return "\n".join(parts) + "\n"


def markdown_table_to_html(lines: list[str]) -> str:
    headers = split_markdown_row(lines[0])
    body_rows = [split_markdown_row(line) for line in lines[1:]]
    html = ["<table>", "<thead><tr>"]
    html.extend(f"<th>{escape(header)}</th>" for header in headers)
    html.extend(["</tr></thead>", "<tbody>"])
    for row in body_rows:
        html.append("<tr>")
        html.extend(f"<td>{inline_markdown_to_html(cell)}</td>" for cell in row)
        html.append("</tr>")
    html.extend(["</tbody>", "</table>"])
    return "\n".join(html)


def split_markdown_row(line: str) -> list[str]:
    return [cell.strip().replace("\\|", "|") for cell in line.strip().strip("|").split("|")]


def inline_markdown_to_html(text: str) -> str:
    escaped = escape(text)
    escaped = re.sub(
        r'&lt;a href=&quot;(.+?)&quot;(.*?)&gt;([^<]+)&lt;/a&gt;',
        lambda match: f'<a href="{match.group(1)}"{match.group(2).replace("&quot;", "\"")}>{match.group(3)}</a>',
        escaped,
    )
    escaped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', escaped)
    return escaped


def validate_report(run_id: str, markdown_path: Path | None = None, runs_dir: Path = RUNS_DIR) -> ValidationResult:
    run_dir = runs_dir / run_id
    markdown_path = markdown_path or run_dir / "report.md"
    try:
        report_input = load_report_input(run_id, runs_dir=runs_dir)
    except FileNotFoundError:
        report_input = {"schema_version": 2, "input_mode": "mechanical_validation_only", "detail_sections": []}
    markdown = markdown_path.read_text(encoding="utf-8")
    errors: list[str] = []
    for banned in BANNED_REPORT_TEXT:
        if banned in markdown:
            errors.append(f"Report contains banned text: {banned}")
    if "| # | Category | User story | Customers / requesters | Distinct customers / people | Opportunity Value Total |" not in markdown:
        errors.append("Summary table header is missing or malformed.")
    if "| Customer / requester | Ask | Evidence | Opportunity Value |" not in markdown:
        errors.append("Detail table header is missing or malformed.")
    if re.search(r'<a href="webexteams://[^"]+"\s+[^>]*target="_blank"', markdown, flags=re.IGNORECASE):
        errors.append("Webex evidence link must not use target=\"_blank\".")
    for section in report_input.get("detail_sections", []):
        anchor = section.get("anchor")
        story = section.get("user_story")
        if f"](#{anchor})" not in markdown:
            errors.append(f"Summary link for story is missing: {story}")
        if f'<a id="{anchor}"></a>' not in markdown:
            errors.append(f"Detail anchor is missing: {anchor}")
        for entry in section.get("entries", []):
            evidence = entry.get("markdown_evidence")
            if evidence and evidence not in markdown:
                errors.append(f"Evidence link missing for {entry.get('customer_requester')}: {evidence}")
            if entry.get("source") == "Webex" and evidence and 'target="_blank"' in evidence:
                errors.append("Webex evidence link must not use target=\"_blank\".")
            if entry.get("source") == "Aha" and entry.get("opportunity_value_numeric") not in (None, ""):
                value = entry.get("opportunity_value")
                if value and value not in markdown:
                    errors.append(f"Aha opportunity value missing from report: {value}")
    numbered_source = re.search(r"\b(?:Webex|Aha)\s+\d{2}\b", markdown)
    if numbered_source:
        errors.append(f"Numbered evidence label found: {numbered_source.group(0)}")
    return ValidationResult(ok=not errors, errors=errors)
