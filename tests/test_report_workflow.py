import json

from pm_assistant.core.report_workflow import (
    build_report_input,
    load_report_format,
    markdown_to_report_html,
    validate_report,
)


ROOM_API_ID = "Y2lzY29zcGFyazovL3VzL1JPT00vNDM4Njk4OTAtNzlkOC0xMWU2LWE4NTMtZjUyY2Y0NmUzNGQy"
MESSAGE_API_ID = "Y2lzY29zcGFyazovL3VzL01FU1NBR0UvOWQzMjA4YzAtNDMyYy0xMWYxLWE1MzgtYzFhODE1ZWNjZjEw"
ROOM_UUID = "43869890-79d8-11e6-a853-f52cf46e34d2"
MESSAGE_UUID = "9d3208c0-432c-11f1-a538-c1a815eccf10"


def test_report_input_preserves_raw_evidence_and_exact_links():
    raw = (
        "Naresh Kumar K S\nHi Subbu. we have customer issue with webhook.\n\n"
        "\"Customer is unable to integrate PagerDuty with Cisco Intersight CVA. "
        "Every attempt results in a 'Connection to host timed out' error and HTTPS requests "
        "to pagerduty.com do not reach their proxy.\"\n"
        "Need support for proxy configuration for webhooks."
    )
    run = {
        "run_id": "r1",
        "feature_name": "webhooks",
        "evidence": [{
            "id": "webex-1",
            "source": "webex",
            "source_type": "webex_message",
            "title": "Ask Intersight",
            "text": raw,
            "requester": "csubrama@cisco.com",
            "created_at": "2026-01-01T00:00:00Z",
            "source_metadata": {
                "room_id": ROOM_API_ID,
                "message_id": MESSAGE_API_ID,
                "room_title": "Ask Intersight",
            },
        }],
    }

    package = build_report_input("webhooks", run)
    assert package["input_mode"] == "raw_evidence_for_codex_review"
    assert "summary_rows" not in package
    assert "detail_sections" not in package
    entry = package["evidence_items"][0]
    assert "Customer is unable to integrate PagerDuty" in entry["raw_evidence"]
    assert entry["evidence_url"] == f"webexteams://im?space={ROOM_UUID}&message={MESSAGE_UUID}"
    assert entry["markdown_evidence"] == f'<a href="webexteams://im?space={ROOM_UUID}&message={MESSAGE_UUID}">Webex</a>'
    assert entry["opportunity_value"] == "Not available"
    assert "Codex must decide" in entry["candidate_reason"]


def test_report_input_preserves_aha_new_window_link_and_value():
    run = {
        "run_id": "r1",
        "feature_name": "webhooks",
        "evidence": [{
            "id": "aha-1",
            "source": "aha",
            "source_type": "aha_idea",
            "title": "Webhook auth",
            "text": "Customer needs bearer token support for webhooks",
            "requester": "Customer A",
            "created_at": "2026-01-01T00:00:00Z",
            "url": "https://example.aha.io/ideas/APP-I-1",
            "source_metadata": {"opportunity_value": "$12,500", "opportunity_value_numeric": 12500},
        }],
    }

    package = build_report_input("webhooks", run)
    entry = package["evidence_items"][0]
    assert entry["markdown_evidence"] == '<a href="https://example.aha.io/ideas/APP-I-1" target="_blank" rel="noopener noreferrer">Aha</a>'
    assert entry["opportunity_value"] == "$12,500"
    assert entry["opportunity_value_numeric"] == 12500
    assert "raw evidence candidates: 0 Webex, 1 Aha" in package["source"]


def test_report_input_contains_review_rubric_and_context():
    run = {
        "run_id": "r1",
        "feature_name": "webhooks",
        "evidence": [{
            "id": "webex-1",
            "source": "webex",
            "source_type": "webex_message",
            "title": "Ask Intersight",
            "text": "Customer asks whether webhook alarm notifications are available.",
            "requester": "person@example.com",
            "created_at": "2026-01-01T00:00:00Z",
            "source_metadata": {
                "room_id": ROOM_API_ID,
                "message_id": MESSAGE_API_ID,
                "source_context": [
                    {"position": "match", "text": "Customer asks whether webhook alarm notifications are available."},
                    {"position": "nearby_thread", "text": "This is already shipped and available."},
                ],
            },
        }],
    }

    package = build_report_input("webhooks", run)

    assert any("internal team chatter" in rule.lower() for rule in package["review_rubric"]["exclude_if"])
    assert any("available" == signal for signal in package["review_rubric"]["resolution_signals"])
    assert package["evidence_items"][0]["source_context"][1]["text"] == "This is already shipped and available."


def test_report_input_does_not_promote_internal_or_resolved_messages_to_rows():
    run = {
        "run_id": "r1",
        "feature_name": "dense GPU server management capabilities",
        "evidence": [
            {
                "id": "webex-meeting-summary",
                "source": "webex",
                "source_type": "webex_message",
                "title": "CC/EC Dryrun",
                "text": (
                    "Summary of meeting. Action Items: Shailendra to update the deck. "
                    "Siddharth to update Jira. Completed on slide 44."
                ),
                "requester": "pm@example.com",
                "created_at": "2026-01-01T00:00:00Z",
            },
            {
                "id": "webex-shipped",
                "source": "webex",
                "source_type": "webex_message",
                "title": "OpenShift plugin",
                "text": "OpenShift Intersight plugin is officially shipped and now available to all customers.",
                "requester": "pm@example.com",
                "created_at": "2026-01-02T00:00:00Z",
            },
        ],
    }

    package = build_report_input("dense GPU server management capabilities", run)

    assert "detail_sections" not in package
    assert "summary_rows" not in package
    assert len(package["evidence_items"]) == 2
    assert all("Codex must decide" in item["candidate_reason"] for item in package["evidence_items"])


def test_markdown_renderer_preserves_link_attributes():
    markdown = "\n".join([
        "# Report",
        "",
        "## Summary Table",
        "",
        "| # | Category | User story | Customers / requesters | Distinct customers / people | Opportunity Value Total |",
        "|---:|---|---|---|---:|---:|",
        "| 1 | Cat | [Story](#cat-story) | A | 1 | Not available |",
        "",
        '<a id="cat-story"></a>',
        "## Cat",
        "",
        "| Customer / requester | Ask | Evidence | Opportunity Value |",
        "|---|---|---|---:|",
        f'| A | Ask. | <a href="webexteams://im?space={ROOM_UUID}&message={MESSAGE_UUID}">Webex</a> | Not available |',
        '| B | Ask. | <a href="https://example.aha.io/ideas/APP-I-1" target="_blank" rel="noopener noreferrer">Aha</a> | $1 |',
    ])
    html = markdown_to_report_html(markdown)
    assert f'href="webexteams://im?space={ROOM_UUID}&amp;message={MESSAGE_UUID}">Webex</a>' in html
    assert 'href="https://example.aha.io/ideas/APP-I-1" target="_blank" rel="noopener noreferrer">Aha</a>' in html
    assert '<a class="back-to-summary" href="#summary">Back to summary</a>' in html


def test_validate_report_catches_old_format_and_bad_links(tmp_path):
    run_dir = tmp_path / "bad-run"
    run_dir.mkdir()
    report_input = {
        "detail_sections": [{
            "anchor": "cat-story",
            "user_story": "Story",
            "entries": [{
                "customer_requester": "A",
                "source": "Webex",
                "markdown_evidence": '<a href="webexteams://im?space=room" target="_blank">Webex</a>',
                "opportunity_value_numeric": None,
            }],
        }]
    }
    (run_dir / "report_input.json").write_text(json.dumps(report_input), encoding="utf-8")
    report = "\n".join([
        "# Report",
        "Related themes: old",
        "| # | Category | User story | Customers / requesters | Distinct customers / people | Opportunity Value Total |",
        "|---:|---|---|---|---:|---:|",
        "| 1 | Cat | [Story](#cat-story) | A | 1 | Not available |",
        "| Customer / requester | Ask | Evidence | Opportunity Value |",
        "|---|---|---|---:|",
        '| A | Ask. | <a href="webexteams://im?space=room" target="_blank">Webex</a> | Not available |',
    ])
    (run_dir / "report.md").write_text(report, encoding="utf-8")

    result = validate_report("bad-run", runs_dir=tmp_path)
    assert not result.ok
    assert any("Related themes:" in error for error in result.errors)
    assert any("Webex evidence link must not use" in error for error in result.errors)


def test_validate_report_checks_bad_webex_links_without_prepared_rows(tmp_path):
    run_dir = tmp_path / "raw-run"
    run_dir.mkdir()
    (run_dir / "report_input.json").write_text(json.dumps({
        "schema_version": 2,
        "input_mode": "raw_evidence_for_codex_review",
        "evidence_items": [],
    }), encoding="utf-8")
    report = "\n".join([
        "# Report",
        "",
        "## Summary Table",
        "",
        "| # | Category | User story | Customers / requesters | Distinct customers / people | Opportunity Value Total |",
        "|---:|---|---|---|---:|---:|",
        "| 1 | Cat | [Story](#cat-story) | A | 1 | Not available |",
        "",
        '<a id="cat-story"></a>',
        "## Cat",
        "",
        "| Customer / requester | Ask | Evidence | Opportunity Value |",
        "|---|---|---|---:|",
        '| A | Ask. | <a href="webexteams://im?space=room" target="_blank">Webex</a> | Not available |',
    ])
    (run_dir / "report.md").write_text(report, encoding="utf-8")

    result = validate_report("raw-run", runs_dir=tmp_path)

    assert not result.ok
    assert any("Webex evidence link must not use" in error for error in result.errors)


def test_validate_report_allows_mechanical_validation_without_report_input(tmp_path):
    run_dir = tmp_path / "no-input-run"
    run_dir.mkdir()
    report = "\n".join([
        "# Report",
        "",
        "## Summary Table",
        "",
        "| # | Category | User story | Customers / requesters | Distinct customers / people | Opportunity Value Total |",
        "|---:|---|---|---|---:|---:|",
        "| 1 | Cat | [Story](#cat-story) | A | 1 | Not available |",
        "",
        '<a id="cat-story"></a>',
        "## Cat",
        "",
        "| Customer / requester | Ask | Evidence | Opportunity Value |",
        "|---|---|---|---:|",
        '| A | Ask. | <a href="webexteams://im?space=room">Webex</a> | Not available |',
    ])
    (run_dir / "report.md").write_text(report, encoding="utf-8")

    result = validate_report("no-input-run", runs_dir=tmp_path)

    assert result.ok


def test_report_format_is_externalized():
    assert "Ask Quality" in load_report_format("feature_feedback")
