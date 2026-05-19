from __future__ import annotations

import argparse
import json
from pathlib import Path

from .auth.intersight_auth import connection_summaries, get as intersight_get
from .connectors import intersight
from .connectors.registry import parse_sources
from .connectors.snowflake import (
    ReadOnlySqlError,
    list_query_templates,
    run_query,
    run_query_template,
    validate_read_only_sql,
)
from .core.report import write_report_files
from .core.adoption import collect_adoption_signals
from .core.pm_workflows import prepare_adoption_summary_input, prepare_prd_input, prepare_snowflake_adoption_summary_input, validate_prd
from .core.report_workflow import prepare_report_input, render_report_html, validate_report
from .core.storage import load_run
from .core.workflows import collect_evidence, coverage_warnings, run_doctor, search_run


def main() -> None:
    parser = argparse.ArgumentParser(description="PM Assistant tools for Codex-driven PM workflows.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="Validate configured source credentials.")
    doctor.add_argument("--sources", default="aha,webex")

    collect = subparsers.add_parser("collect", help="Collect evidence for a topic/product area.")
    collect.add_argument("--topic")
    collect.add_argument("--feature", help="Backward-compatible alias for --topic.")
    collect.add_argument("--sources", required=True)
    collect.add_argument("--config")
    collect.add_argument("--date-range")

    search = subparsers.add_parser("search", help="Search evidence from a saved run.")
    search.add_argument("--run-id")
    search.add_argument("--query", required=True)
    search.add_argument("--sources")
    search.add_argument("--limit", type=int, default=20)

    skeleton = subparsers.add_parser("report-skeleton", help="Legacy/debug: create a code-generated Markdown report draft.")
    skeleton.add_argument("--run-id", required=True)
    skeleton.add_argument("--output", required=True)

    prepare = subparsers.add_parser("prepare-report", help="Prepare raw evidence review input for Codex-authored reports.")
    prepare.add_argument("--run-id", required=True)
    prepare.add_argument("--topic")
    prepare.add_argument("--feature", help="Backward-compatible alias for --topic.")
    prepare.add_argument("--format", default="feature_feedback")

    prepare_prd = subparsers.add_parser("prepare-prd", help="Prepare feedback and optional research input for a Codex-authored PRD.")
    prepare_prd.add_argument("--run-id", required=True)
    prepare_prd.add_argument("--topic")
    prepare_prd.add_argument("--feature", help="Backward-compatible alias for --topic.")
    prepare_prd.add_argument("--research-run-id")

    validate = subparsers.add_parser("validate-report", help="Validate a Codex-authored Markdown report.")
    validate.add_argument("--run-id", required=True)
    validate.add_argument("--markdown")

    render = subparsers.add_parser("render-report", help="Render report.html from a Codex-authored Markdown report.")
    render.add_argument("--run-id", required=True)
    render.add_argument("--markdown")

    validate_prd_parser = subparsers.add_parser("validate-prd", help="Validate a Codex-authored PRD.")
    validate_prd_parser.add_argument("--run-id", required=True)
    validate_prd_parser.add_argument("--markdown")

    snowflake_templates = subparsers.add_parser("snowflake-templates", help="List bundled Snowflake SQL templates.")

    snowflake_validate = subparsers.add_parser("snowflake-validate", help="Validate read-only Snowflake SQL.")
    snowflake_validate.add_argument("--sql", required=True)

    snowflake_query = subparsers.add_parser("snowflake-query", help="Run read-only Snowflake SQL or a bundled template.")
    snowflake_query.add_argument("--sql")
    snowflake_query.add_argument("--template")
    snowflake_query.add_argument("--max-rows", type=int, default=100)

    adoption = subparsers.add_parser("prepare-adoption", help="Prepare generic adoption summary input from collected signals.")
    adoption.add_argument("--topic", required=True)
    adoption.add_argument("--sources", default="snowflake")
    adoption.add_argument("--account", default="all", choices=["us", "eu", "all", "default"])
    adoption.add_argument("--template")
    adoption.add_argument("--max-rows", type=int, default=100)
    adoption.add_argument("--run-id")

    collect_adoption = subparsers.add_parser("collect-adoption", help="Collect generic adoption signals from one or more sources.")
    collect_adoption.add_argument("--topic", required=True)
    collect_adoption.add_argument("--sources", default="snowflake,intersight")
    collect_adoption.add_argument("--account", default="all", choices=["us", "eu", "all", "default"])
    collect_adoption.add_argument("--template")
    collect_adoption.add_argument("--max-rows", type=int, default=100)
    collect_adoption.add_argument("--save", action="store_true")

    intersight_doctor = subparsers.add_parser("intersight-doctor", help="Validate Intersight API key auth for one or all profiles.")
    intersight_doctor.add_argument("--account", default="all", choices=["us", "eu", "all", "default"])
    intersight_doctor.add_argument("--path", default="/api/v1/iam/Accounts")

    intersight_get_parser = subparsers.add_parser("intersight-get", help="Run a read-only Intersight GET request for a profile.")
    intersight_get_parser.add_argument("--account", required=True, choices=["us", "eu", "default"])
    intersight_get_parser.add_argument("--path", required=True)

    intersight_query = subparsers.add_parser("intersight-query", help="Query an Intersight object type read-only.")
    intersight_query.add_argument("--account", default="all", choices=["us", "eu", "all", "default"])
    intersight_query.add_argument("--object-type", required=True)
    intersight_query.add_argument("--filters", default="{}")
    intersight_query.add_argument("--top", type=int, default=100)

    intersight_count = subparsers.add_parser("intersight-count", help="Count Intersight objects by type.")
    intersight_count.add_argument("--account", default="all", choices=["us", "eu", "all", "default"])
    intersight_count.add_argument("--object-type", required=True)
    intersight_count.add_argument("--filters", default="{}")

    intersight_inventory = subparsers.add_parser("intersight-inventory", help="Summarize Intersight inventory signals.")
    intersight_inventory.add_argument("--account", default="all", choices=["us", "eu", "all", "default"])
    intersight_inventory.add_argument("--save", action="store_true")

    intersight_health = subparsers.add_parser("intersight-health", help="Summarize Intersight health/friction signals.")
    intersight_health.add_argument("--account", default="all", choices=["us", "eu", "all", "default"])
    intersight_health.add_argument("--save", action="store_true")

    intersight_impact = subparsers.add_parser("intersight-impact", help="Run a read-only Intersight impact query from criteria JSON.")
    intersight_impact.add_argument("--account", default="all", choices=["us", "eu", "all", "default"])
    intersight_impact.add_argument("--criteria", default="{}")
    intersight_impact.add_argument("--save", action="store_true")

    subparsers.add_parser("mcp", help="Run the MCP server over stdio.")
    args = parser.parse_args()

    if args.command == "doctor":
        results = run_doctor(parse_sources(args.sources))
        for source, messages in results.items():
            print(f"[{source}]")
            for message in messages:
                print(f"- {message}")
        return

    if args.command == "collect":
        topic = require_topic(args)
        run = collect_evidence(topic, parse_sources(args.sources), config_path=args.config, date_range=args.date_range)
        print(f"Run ID: {run.run_id}")
        print(f"Evidence items: {len(run.evidence)}")
        if run.warnings:
            print("Warnings:")
            for warning in run.warnings:
                print(f"- {warning}")
        return

    if args.command == "search":
        sources = parse_sources(args.sources) if args.sources else None
        for item in search_run(args.query, run_id=args.run_id, sources=sources, limit=args.limit):
            print(f"[{item['source']}] {item['id']} - {item['title']}")
            print(f"  requester: {item.get('requester') or item.get('author') or 'Unknown'}")
            print(f"  {item['text'][:300]}")
        return

    if args.command == "report-skeleton":
        run = load_run(args.run_id)
        path = Path(args.output)
        outputs = write_report_files(run.get("feature_name") or args.run_id, run, path)
        print(f"Wrote Markdown: {outputs['markdown']}")
        print(f"Wrote HTML: {outputs['html']}")
        for warning in coverage_warnings(run):
            print(f"Warning: {warning}")
        return

    if args.command == "prepare-report":
        run = load_run(args.run_id)
        topic = args.topic or args.feature or run.get("feature_name") or args.run_id
        package = prepare_report_input(topic, args.run_id, format_name=args.format)
        print(f"Wrote report input: runs\\{args.run_id}\\report_input.json")
        print(f"Input mode: {package.get('input_mode')}")
        print(f"Evidence items prepared: {len(package.get('evidence_items', []))}")
        return

    if args.command == "prepare-prd":
        run = load_run(args.run_id)
        topic = args.topic or args.feature or run.get("feature_name") or args.run_id
        package = prepare_prd_input(topic, args.run_id, research_run_id=args.research_run_id)
        print(f"Wrote PRD input: runs\\{args.run_id}\\prd_input.json")
        print(f"Evidence items prepared: {len(package.get('feedback', {}).get('evidence_items', []))}")
        return

    if args.command == "validate-report":
        result = validate_report(args.run_id, Path(args.markdown) if args.markdown else None)
        print("OK" if result.ok else "FAILED")
        for error in result.errors:
            print(f"- {error}")
        raise SystemExit(0 if result.ok else 1)

    if args.command == "render-report":
        output = render_report_html(args.run_id, Path(args.markdown) if args.markdown else None)
        print(f"Wrote HTML: {output}")
        return

    if args.command == "validate-prd":
        result = validate_prd(args.run_id, Path(args.markdown) if args.markdown else None)
        print("OK" if result["ok"] else "FAILED")
        for error in result["errors"]:
            print(f"- {error}")
        raise SystemExit(0 if result["ok"] else 1)

    if args.command == "snowflake-templates":
        for name in list_query_templates():
            print(name)
        return

    if args.command == "snowflake-validate":
        try:
            print(validate_read_only_sql(args.sql))
        except ReadOnlySqlError as exc:
            print(f"FAILED: {exc}")
            raise SystemExit(1)
        return

    if args.command == "snowflake-query":
        result = run_snowflake_cli_query(args)
        print_json(result)
        return

    if args.command == "prepare-adoption":
        signals = collect_adoption_signals(
            args.topic,
            parse_sources(args.sources),
            account=args.account,
            snowflake_template=args.template,
            max_rows=args.max_rows,
        )
        package = prepare_adoption_summary_input(args.topic, signals, run_id=args.run_id)
        print(f"Wrote adoption input: {package['input_path']}")
        print(f"Sources: {', '.join(package.get('sources', []))}")
        return

    if args.command == "collect-adoption":
        signals = collect_adoption_signals(
            args.topic,
            parse_sources(args.sources),
            account=args.account,
            snowflake_template=args.template,
            max_rows=args.max_rows,
        )
        if args.save:
            package = prepare_adoption_summary_input(args.topic, signals)
            print_json({"input_path": package["input_path"], "signals": signals})
        else:
            print_json(signals)
        return

    if args.command == "intersight-doctor":
        print_json(connection_summaries(args.account, path=args.path))
        return

    if args.command == "intersight-get":
        response = intersight_get(args.path, account=args.account, timeout=30)
        response.raise_for_status()
        print_json(response.json())
        return

    if args.command == "intersight-query":
        print_json(intersight.query(args.account, args.object_type, filters=parse_json_arg(args.filters), top=args.top))
        return

    if args.command == "intersight-count":
        print_json(intersight.count(args.account, args.object_type, filters=parse_json_arg(args.filters)))
        return

    if args.command == "intersight-inventory":
        print_json(intersight.inventory_summary(args.account, save=args.save))
        return

    if args.command == "intersight-health":
        print_json(intersight.health_summary(args.account, save=args.save))
        return

    if args.command == "intersight-impact":
        print_json(intersight.impact_analysis(args.account, criteria=parse_json_arg(args.criteria), save=args.save))
        return

    if args.command == "mcp":
        from .mcp_server import main as mcp_main
        mcp_main()

def require_topic(args: argparse.Namespace) -> str:
    topic = args.topic or args.feature
    if not topic:
        raise SystemExit("Missing required topic. Use --topic or the backward-compatible --feature option.")
    return topic


def run_snowflake_cli_query(args: argparse.Namespace) -> dict:
    if bool(args.sql) == bool(args.template):
        raise SystemExit("Provide exactly one of --sql or --template.")
    if args.template:
        return run_query_template(args.template, max_rows=args.max_rows)
    return run_query(args.sql, max_rows=args.max_rows)


def print_json(data: dict) -> None:
    print(json.dumps(data, indent=2))


def parse_json_arg(value: str) -> dict:
    parsed = json.loads(value or "{}")
    if not isinstance(parsed, dict):
        raise SystemExit("Expected a JSON object.")
    return parsed


if __name__ == "__main__":
    main()
