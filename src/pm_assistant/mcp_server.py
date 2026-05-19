from __future__ import annotations

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .auth.intersight_auth import connection_summaries as intersight_connection_summaries
from .auth.intersight_auth import get as intersight_read
from .connectors import intersight
from .connectors.jira import JiraConnector, escape_jql
from .connectors.registry import parse_sources
from .connectors.snowflake import (
    ReadOnlySqlError,
    connection_summary as snowflake_connection_summary_workflow,
    list_query_templates,
    load_query_template,
    run_query as run_snowflake_query,
    run_query_template,
    validate_read_only_sql,
)
from .core.config import load_environment, load_feature_config
from .core.adoption import collect_adoption_signals as collect_adoption_signals_workflow
from .core.report import build_report_html, build_report_skeleton as make_skeleton, write_report_files
from .core.report_workflow import (
    load_report_format,
    load_report_input,
    prepare_report_input as prepare_report_input_workflow,
    render_report_html as render_report_html_workflow,
    validate_report as validate_report_workflow,
)
from .core.pm_workflows import (
    load_research_packet,
    prepare_adoption_summary_input,
    prepare_jira_update_input,
    prepare_prd_input as prepare_prd_input_workflow,
    save_research_packet as save_research_packet_workflow,
    validate_prd as validate_prd_workflow,
)
from .core.storage import latest_run_id, load_run
from .core.workflows import collect_evidence as collect_workflow
from .core.workflows import coverage_warnings, run_doctor, search_run

mcp = FastMCP("PM Assistant")


@mcp.tool()
def doctor(sources: list[str] | str = "aha,webex") -> dict:
    """Validate source credentials and return setup guidance."""
    return run_doctor(parse_sources(sources))


@mcp.tool()
def collect_evidence(feature_name: str, sources: list[str] | str, date_range: str | None = None, config: str | None = None) -> dict:
    """Collect feature evidence from explicit sources and save a local run."""
    run = collect_workflow(feature_name, parse_sources(sources), config_path=config, date_range=date_range)
    return {
        "run_id": run.run_id,
        "feature_name": run.feature_name,
        "sources": run.sources,
        "evidence_count": len(run.evidence),
        "warnings": run.warnings,
        "next_steps": [
            f"Read evidence://{run.run_id}",
            "Read report-format://feature_feedback",
            "Codex should semantically review raw evidence and source_context before writing report.md",
            f"Write runs/{run.run_id}/report.md in the required format",
            f"Call validate_report(run_id='{run.run_id}')",
            f"Call render_report_html(run_id='{run.run_id}')",
        ],
    }


@mcp.tool()
def collect_pm_evidence(topic: str, sources: list[str] | str, date_range: str | None = None, config: str | None = None) -> dict:
    """Collect PM evidence for a topic/product area from explicit internal sources."""
    result = collect_evidence(topic, sources, date_range=date_range, config=config)
    result["topic"] = topic
    result["next_steps"] = [
        f"Read evidence://{result['run_id']}",
        "For feedback scans, read report-format://feature_feedback and call prepare_report_input.",
        "For PRDs, optionally collect/save research, then call prepare_prd_input.",
        "Codex should synthesize and write the final PM artifact.",
    ]
    return result


@mcp.tool()
def collect_and_generate_report(feature_name: str, sources: list[str] | str, date_range: str | None = None, config: str | None = None) -> dict:
    """Legacy/debug path: collect evidence and return code-generated draft reports, not the preferred final report workflow."""
    run = collect_workflow(feature_name, parse_sources(sources), config_path=config, date_range=date_range)
    output_paths = write_report_files(feature_name, run.to_dict(), Path("runs") / run.run_id / "report.md")
    coverage = coverage_warnings(run.to_dict())
    return {
        "run_id": run.run_id,
        "feature_name": run.feature_name,
        "sources": run.sources,
        "evidence_count": len(run.evidence),
        "warnings": [*run.warnings, *coverage],
        "markdown_path": str(output_paths["markdown"]),
        "html_path": str(output_paths["html"]),
        "markdown": make_skeleton(feature_name, run.to_dict()),
        "html": build_report_html(feature_name, run.to_dict()),
    }


@mcp.tool()
def search_evidence(query: str, sources: list[str] | str | None = None, limit: int = 20, run_id: str | None = None) -> list[dict]:
    """Search collected evidence in a saved run."""
    parsed_sources = parse_sources(sources) if sources else None
    return search_run(query, run_id=run_id, sources=parsed_sources, limit=limit)


@mcp.tool()
def search_pm_evidence(query: str, sources: list[str] | str | None = None, limit: int = 20, run_id: str | None = None) -> list[dict]:
    """Search PM evidence in a saved run."""
    return search_evidence(query, sources=sources, limit=limit, run_id=run_id)


@mcp.tool()
def jira_read_issue(issue_key: str) -> dict:
    """Read a Jira issue by key using configured Jira credentials."""
    load_environment()
    return JiraConnector().read_issue(issue_key)


@mcp.tool()
def jira_search(query: str, max_results: int = 20) -> list[dict]:
    """Search Jira issues with a safe text query and return normalized issue summaries."""
    load_environment()
    connector = JiraConnector()
    safe_limit = max(1, min(int(max_results), 50))
    jql = f'text ~ "{escape_jql(query)}" ORDER BY updated DESC'
    return [connector.read_issue(issue["key"]) for issue in connector.search_issues(jql, max_results=safe_limit)]


@mcp.tool()
def jira_add_comment(
    issue_key: str,
    comment: str,
    mention_account_id: str | None = None,
    mention_display_name: str | None = None,
) -> dict:
    """Add a Jira issue comment. Supplying a mention account ID creates a real Jira @mention."""
    load_environment()
    return JiraConnector().add_comment(
        issue_key,
        comment,
        mention_account_id=mention_account_id,
        mention_display_name=mention_display_name,
    )


@mcp.tool()
def build_report_skeleton(feature_name: str, run_id: str) -> dict:
    """Legacy/debug path: build code-generated Markdown and HTML drafts from a saved evidence run."""
    run = load_run(run_id)
    output_paths = write_report_files(feature_name, run, Path("runs") / run_id / "report.md")
    coverage = coverage_warnings(run)
    return {
        "run_id": run_id,
        "markdown_path": str(output_paths["markdown"]),
        "html_path": str(output_paths["html"]),
        "warnings": coverage,
        "markdown": make_skeleton(feature_name, run),
        "html": build_report_html(feature_name, run),
    }


@mcp.tool()
def prepare_report_input(feature_name: str, run_id: str, format_name: str = "feature_feedback") -> dict:
    """Prepare raw evidence and review guidance for a Codex-authored report."""
    package = prepare_report_input_workflow(feature_name, run_id, format_name=format_name)
    return {
        "run_id": run_id,
        "feature_name": feature_name,
        "format_name": format_name,
        "report_input_path": str(Path("runs") / run_id / "report_input.json"),
        "input_mode": package.get("input_mode"),
        "evidence_items": len(package.get("evidence_items", [])),
        "next_steps": [
            f"Read evidence://{run_id} or report-input://{run_id}",
            f"Read report-format://{format_name}",
            "Codex should semantically review raw evidence and source_context, excluding internal/resolved/unrelated items",
            f"Write runs/{run_id}/report.md using the report format",
            f"Call validate_report(run_id='{run_id}')",
            f"Call render_report_html(run_id='{run_id}')",
        ],
    }


@mcp.tool()
def validate_report(run_id: str, markdown_path: str | None = None) -> dict:
    """Validate a Codex-authored report.md against prepared report input."""
    result = validate_report_workflow(run_id, Path(markdown_path) if markdown_path else None)
    return result.to_dict()


@mcp.tool()
def render_report_html(run_id: str, markdown_path: str | None = None) -> dict:
    """Render report.html from a validated Markdown report."""
    html_path = render_report_html_workflow(run_id, Path(markdown_path) if markdown_path else None)
    return {"run_id": run_id, "html_path": str(html_path)}


@mcp.tool()
def prepare_prd_input(topic: str, run_id: str, research_run_id: str | None = None) -> dict:
    """Prepare evidence and optional research for a Codex-authored PRD."""
    package = prepare_prd_input_workflow(topic, run_id, research_run_id=research_run_id)
    return {
        "run_id": run_id,
        "topic": topic,
        "research_run_id": research_run_id,
        "prd_input_path": str(Path("runs") / run_id / "prd_input.json"),
        "evidence_items": len(package.get("feedback", {}).get("evidence_items", [])),
        "next_steps": [
            f"Read prd-input://{run_id}",
            "Read report-format://prd",
            f"Write runs/{run_id}/prd.md",
            f"Call validate_prd(run_id='{run_id}')",
        ],
    }


@mcp.tool()
def validate_prd(run_id: str, markdown_path: str | None = None) -> dict:
    """Validate a Codex-authored PRD for required PM sections and citations."""
    return validate_prd_workflow(run_id, Path(markdown_path) if markdown_path else None)


@mcp.tool()
def save_research_packet(topic: str, findings: list[dict] | dict, citations: list[dict] | None = None, run_id: str | None = None) -> dict:
    """Save cited external desk research as a separate research packet."""
    return save_research_packet_workflow(topic, findings, citations=citations, run_id=run_id)


@mcp.tool()
def prepare_jira_update(issue_key: str, run_id: str | None = None, artifact_path: str | None = None) -> dict:
    """Prepare a Jira update/comment draft input from an issue and optional evidence run."""
    load_environment()
    issue = JiraConnector().read_issue(issue_key)
    package = prepare_jira_update_input(issue, run_id=run_id, artifact_path=artifact_path)
    return {
        "issue_key": issue_key,
        "run_id": run_id,
        "input_path": package["input_path"],
        "next_steps": [
            "Read report-format://jira_update",
            "Write a concise Jira update draft.",
            "Only call jira_add_comment after the user explicitly asks to post it.",
        ],
    }


@mcp.tool()
def snowflake_connection_summary() -> dict:
    """Test configured Snowflake credentials and return connection context."""
    load_environment()
    return snowflake_connection_summary_workflow()


@mcp.tool()
def snowflake_validate_sql(sql: str) -> dict:
    """Validate that a Snowflake SQL statement is read-only and single-statement."""
    try:
        return {"ok": True, "sql": validate_read_only_sql(sql), "errors": []}
    except ReadOnlySqlError as exc:
        return {"ok": False, "sql": "", "errors": [str(exc)]}


@mcp.tool()
def snowflake_query(sql: str, max_rows: int = 100) -> dict:
    """Run read-only Snowflake SQL and return a JSON-safe preview result."""
    load_environment()
    return run_snowflake_query(sql, max_rows=max_rows)


@mcp.tool()
def list_snowflake_queries() -> list[str]:
    """List bundled read-only Snowflake SQL templates."""
    return list_query_templates()


@mcp.tool()
def run_snowflake_query_template(name: str, max_rows: int = 100) -> dict:
    """Run a bundled read-only Snowflake SQL template by file name."""
    load_environment()
    return run_query_template(name, max_rows=max_rows)


@mcp.tool()
def collect_adoption_signals(topic: str, sources: list[str] | str = "snowflake,intersight", account: str = "all", snowflake_template: str | None = None, max_rows: int = 100, save: bool = False) -> dict:
    """Collect source-agnostic adoption signals from Snowflake, Intersight, or future sources."""
    load_environment()
    signals = collect_adoption_signals_workflow(
        topic,
        parse_sources(sources),
        account=account,
        snowflake_template=snowflake_template,
        max_rows=max_rows,
    )
    if not save:
        return signals
    package = prepare_adoption_summary_input(topic, signals)
    return {"input_path": package["input_path"], "run_id": package["run_id"], "signals": signals}


@mcp.tool()
def prepare_adoption_summary(topic: str, sources: list[str] | str = "snowflake,intersight", account: str = "all", snowflake_template: str | None = None, max_rows: int = 100, run_id: str | None = None) -> dict:
    """Prepare generic multi-source adoption input for a Codex-authored summary."""
    load_environment()
    signals = collect_adoption_signals_workflow(
        topic,
        parse_sources(sources),
        account=account,
        snowflake_template=snowflake_template,
        max_rows=max_rows,
    )
    package = prepare_adoption_summary_input(topic, signals, run_id=run_id)
    return {
        "run_id": package["run_id"],
        "topic": topic,
        "input_path": package["input_path"],
        "sources": package.get("sources", []),
        "warnings": package.get("warnings", []),
        "next_steps": [
            f"Read adoption-input://{package['run_id']}",
            "Read report-format://adoption_summary",
            f"Write runs/{package['run_id']}/adoption_summary.md",
        ],
    }


@mcp.tool()
def intersight_connection_summary(account: str = "all", path: str = "/api/v1/iam/Accounts") -> dict:
    """Validate read-only signed Intersight API access for account us, eu, default, or all."""
    return intersight_connection_summaries(account, path=path)


@mcp.tool()
def intersight_get(account: str, path: str) -> dict:
    """Run a read-only Intersight GET request for a configured account profile."""
    response = intersight_read(path, account=account, timeout=30)
    response.raise_for_status()
    return response.json()


@mcp.tool()
def intersight_query(account: str, object_type: str, filters: dict | str | None = None, top: int = 100) -> dict:
    """Query an Intersight object type read-only across one account or all accounts."""
    return intersight.query(account, object_type, filters=filters, top=top)


@mcp.tool()
def intersight_count(account: str, object_type: str, filters: dict | str | None = None) -> dict:
    """Count Intersight objects by type across one account or all accounts."""
    return intersight.count(account, object_type, filters=filters)


@mcp.tool()
def intersight_inventory_summary(account: str = "all", save: bool = False) -> dict:
    """Summarize Intersight inventory signals across one account or all accounts."""
    return intersight.inventory_summary(account, save=save)


@mcp.tool()
def intersight_health_summary(account: str = "all", save: bool = False) -> dict:
    """Summarize Intersight alarms/advisories across one account or all accounts."""
    return intersight.health_summary(account, save=save)


@mcp.tool()
def intersight_impact_analysis(account: str = "all", criteria: dict | None = None, save: bool = False) -> dict:
    """Run a read-only Intersight impact query from criteria."""
    return intersight.impact_analysis(account, criteria=criteria, save=save)


@mcp.resource("evidence://{run_id}")
def evidence_resource(run_id: str) -> str:
    """Return normalized evidence JSON for a run."""
    return json.dumps(load_run(run_id), indent=2)


@mcp.resource("report-input://{run_id}")
def report_input_resource(run_id: str) -> str:
    """Return prepared structured report input for a run."""
    return json.dumps(load_report_input(run_id), indent=2)


@mcp.resource("prd-input://{run_id}")
def prd_input_resource(run_id: str) -> str:
    """Return prepared PRD input for a run."""
    path = Path("runs") / run_id / "prd_input.json"
    if not path.exists():
        raise FileNotFoundError(f"PRD input for run '{run_id}' was not found at {path}")
    return path.read_text(encoding="utf-8")


@mcp.resource("research://{run_id}")
def research_resource(run_id: str) -> str:
    """Return a saved external research packet."""
    return json.dumps(load_research_packet(run_id), indent=2)


@mcp.resource("adoption-input://{run_id}")
def adoption_input_resource(run_id: str) -> str:
    """Return prepared adoption summary input for a Snowflake run."""
    path = Path("runs") / run_id / "adoption_input.json"
    if not path.exists():
        raise FileNotFoundError(f"Adoption input for run '{run_id}' was not found at {path}")
    return path.read_text(encoding="utf-8")


@mcp.resource("snowflake-query://{name}")
def snowflake_query_resource(name: str) -> str:
    """Return a bundled Snowflake SQL template."""
    return load_query_template(name)


@mcp.resource("report-format://{format_name}")
def report_format_resource(format_name: str) -> str:
    """Return an external report format/instructions document."""
    return load_report_format(format_name)


@mcp.resource("run://{run_id}/summary")
def run_summary_resource(run_id: str) -> str:
    """Return a compact run summary."""
    run = load_run(run_id)
    return json.dumps({
        "run_id": run.get("run_id"),
        "feature_name": run.get("feature_name"),
        "created_at": run.get("created_at"),
        "sources": run.get("sources"),
        "evidence_count": len(run.get("evidence", [])),
        "warnings": run.get("warnings", []),
    }, indent=2)


@mcp.resource("config://feature/{feature_name}")
def feature_config_resource(feature_name: str) -> str:
    """Return the effective feature config."""
    config = load_feature_config(feature_name)
    return json.dumps({
        "feature_name": config.feature_name,
        "aliases": config.aliases,
        "related_terms": config.related_terms,
        "exclude_terms": config.exclude_terms,
        "source_filters": config.source_filters,
        "category_hints": config.category_hints,
    }, indent=2)


@mcp.resource("config://topic/{topic}")
def topic_config_resource(topic: str) -> str:
    """Return the effective topic/product-area config."""
    return feature_config_resource(topic)


@mcp.prompt()
def analyze_feature_feedback(feature_name: str, run_id: str | None = None) -> str:
    """Prompt Codex to analyze feature feedback using collected evidence."""
    resolved_run_id = run_id or latest_run_id() or "<collect evidence first>"
    template = report_template()
    return f"""
Analyze customer feedback for feature: {feature_name}

Use only evidence from evidence://{resolved_run_id}. Do not invent customers, request counts, dates, links, or asks.

Produce report artifacts with:
1. If evidence has not been collected, call collect_evidence first.
2. Read evidence://{resolved_run_id} and report-format://feature_feedback. Optionally call prepare_report_input only for a packaged raw-evidence review file.
3. Review raw evidence and any source_context yourself. Do not trust code-generated candidates as final report rows.
4. Exclude internal team chatter, meeting summaries, deck/Jira/process action items, announcements, FYIs, support answers, roadmap debate, and any ask later shown as available, shipped, fixed, resolved, answered, or closed in the same context.
5. Include only real unresolved customer/requester asks, pain points, gaps, or enhancement requests with evidence links.
6. Write runs/{resolved_run_id}/report.md exactly in the report format.
7. Call validate_report, fix any validation failures, then call render_report_html.

If the user asks to create or generate the report, produce both canonical files: report.md and report.html. Tell the user to open report.html in Edge/Chrome for working anchors and Webex app links.
Honor any feature-specific profile in configs/ for categories, request filters, summaries, and user-story wording.
If evidence is thin, say so clearly. Keep collection warnings in tool metadata; do not add a Collection Warnings section to the user-facing report.

Report template:

{template}
""".strip()


@mcp.prompt()
def feedback_scan(topic: str, run_id: str | None = None) -> str:
    """Prompt Codex to scan feedback for top PM gaps and themes."""
    resolved_run_id = run_id or latest_run_id() or "<collect evidence first>"
    return f"""
Scan PM feedback for topic: {topic}

Use evidence://{resolved_run_id}. If evidence has not been collected, call collect_pm_evidence first.
Identify the top product gaps, affected customers/requesters, supporting evidence links, and what is still unresolved.
Keep internal evidence separate from external research. Do not invent customers, counts, values, or dates.
""".strip()


@mcp.prompt()
def write_prd(topic: str, run_id: str | None = None, research_run_id: str | None = None) -> str:
    """Prompt Codex to draft a PRD from PM evidence and optional research."""
    resolved_run_id = run_id or latest_run_id() or "<collect evidence first>"
    return f"""
Write a PRD for topic: {topic}

1. If needed, call collect_pm_evidence.
2. Call prepare_prd_input(topic='{topic}', run_id='{resolved_run_id}', research_run_id={research_run_id!r}).
3. Read prd-input://{resolved_run_id} and report-format://prd.
4. Write runs/{resolved_run_id}/prd.md.
5. Call validate_prd and fix validation failures.

Use internal feedback for customer evidence and cited external research only when a research packet is available.
""".strip()


def main() -> None:
    mcp.run()


def report_template() -> str:
    path = Path(__file__).resolve().parents[2] / "prompts" / "feature_feedback_report.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return "Use the standard feature feedback report format with summary table, category sections, source citations, and raw excerpts."


if __name__ == "__main__":
    main()
