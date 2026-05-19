from pm_assistant.connectors.aha import AhaConnector
from pm_assistant.connectors.aha import opportunity_value_from_idea
from pm_assistant.connectors.aha import requester_from_idea
from pm_assistant.core.report import build_actionable_ask, build_report_html, build_report_skeleton, decoded_webex_resource_id


ROOM_API_ID = "Y2lzY29zcGFyazovL3VzL1JPT00vNDM4Njk4OTAtNzlkOC0xMWU2LWE4NTMtZjUyY2Y0NmUzNGQy"
MESSAGE_API_ID = "Y2lzY29zcGFyazovL3VzL01FU1NBR0UvOWQzMjA4YzAtNDMyYy0xMWYxLWE1MzgtYzFhODE1ZWNjZjEw"
ROOM_UUID = "43869890-79d8-11e6-a853-f52cf46e34d2"
MESSAGE_UUID = "9d3208c0-432c-11f1-a538-c1a815eccf10"


def test_aha_idea_normalization():
    connector = AhaConnector()
    connector.domain = "example.aha.io"
    evidence = connector.idea_to_evidence({
        "reference_num": "APP-I-1",
        "name": "Webhook auth",
        "description": "<p>Need bearer token support</p>",
        "created_by": {"email": "pm@example.com"},
        "created_at": "2026-01-01T00:00:00Z",
        "custom_fields": {"Account Name": "Example Customer"},
    })
    assert evidence.source == "aha"
    assert evidence.requester == "Example Customer"
    assert "bearer token" in evidence.text


def test_decodes_webex_api_resource_ids():
    assert decoded_webex_resource_id(ROOM_API_ID) == ROOM_UUID
    assert decoded_webex_resource_id(MESSAGE_API_ID) == MESSAGE_UUID
    assert decoded_webex_resource_id(ROOM_UUID) == ROOM_UUID
    assert decoded_webex_resource_id("not-a-webex-id") == ""


def test_aha_idea_extracts_opportunity_value():
    display, numeric = opportunity_value_from_idea({
        "custom_fields": [
            {"key": "opportunity_value", "name": "Opportunity Value", "value": "$12,500"}
        ]
    })
    assert display == "$12,500"
    assert numeric == 12500


def test_aha_idea_extracts_shorthand_opportunity_value():
    display, numeric = opportunity_value_from_idea({
        "custom_fields": [
            {"key": "opportunity_value", "name": "Opportunity Value", "value": {"display_value": "$1M"}}
        ]
    })
    assert display == "$1M"
    assert numeric == 1000000


def test_aha_idea_formats_numeric_opportunity_value_as_currency():
    display, numeric = opportunity_value_from_idea({
        "custom_fields": [
            {"key": "opportunity_value", "name": "Opportunity Value", "value": 1000000.0}
        ]
    })
    assert display == "$1,000,000"
    assert numeric == 1000000


def test_report_skeleton_is_generic():
    report = build_report_skeleton("audit logs", {"run_id": "r1", "evidence": [], "warnings": []})
    assert "Audit Logs Feature Enhancement Feedback Report" in report
    assert "No Reportable Feedback Found" in report


def test_report_generated_timestamp_uses_pacific_timezone():
    report = build_report_skeleton("audit logs", {"run_id": "r1", "evidence": [], "warnings": []})
    generated_line = next(line for line in report.splitlines() if line.startswith("Generated on:"))
    assert generated_line.endswith(" PST") or generated_line.endswith(" PDT")
    assert not generated_line.endswith(" UTC")
    assert "Generated:" not in report


def test_report_hides_warnings_and_numbers_summary_rows():
    run = {
        "run_id": "r1",
        "warnings": ["secret debug warning"],
        "evidence": [{
            "id": "aha-idea-APP-I-1",
            "source": "aha",
            "source_type": "aha_idea",
            "title": "Webhook auth",
            "text": "Customer needs bearer token support for webhooks",
            "author": "pm@example.com",
            "requester": "Example Customer",
            "created_at": "2026-01-01T00:00:00Z",
            "url": "https://example.aha.io/ideas/APP-I-1",
            "source_metadata": {"reference_num": "APP-I-1", "workflow_status": "Under consideration", "score": 42},
        }],
    }
    report = build_report_skeleton("webhooks", run)
    assert "Collection Warnings" not in report
    assert "Collection:" not in report
    assert "secret debug warning" not in report
    assert "Source: matching evidence: 0 Webex, 1 Aha (1 ideas, 0 comments); 1 report entries after filtering likely asks and deduplicating exact repeats" in report
    assert "Source: `evidence.json`" not in report
    assert "| # | Category | User story | Customers / requesters | Distinct customers / people | Opportunity Value Total |" in report
    assert "| 1 | Authentication and Authorization |" in report
    assert "| Customer / requester | Ask | Evidence | Opportunity Value |" in report
    assert '<a href="https://example.aha.io/ideas/APP-I-1" target="_blank" rel="noopener noreferrer">Aha</a>' in report
    assert "Aha ref `APP-I-1`" not in report
    assert "status `Under consideration`" not in report
    assert "score `42`" not in report
    assert "#### 1. Customer: Example Customer" not in report
    assert "Raw feedback:" not in report
    assert "Feature ask:" not in report
    assert "Related themes:" not in report
    assert "Example Customer" in report


def test_html_report_has_real_anchors_and_webex_links():
    run = {
        "run_id": "r1",
        "warnings": ["hidden"],
        "evidence": [{
            "id": "webex-message-1",
            "source": "webex",
            "source_type": "webex_message",
            "title": "Ask Intersight",
            "text": "Customer needs webhook delivery for alarms",
            "author": "person@example.com",
            "requester": "person@example.com",
            "created_at": "2026-01-01T00:00:00Z",
            "source_metadata": {
                "space_link": f"webexteams://im?space={ROOM_API_ID}",
                "room_id": ROOM_API_ID,
                "message_id": MESSAGE_API_ID,
                "room_title": "Ask Intersight",
            },
        }],
    }
    html = build_report_html("webhooks", run)
    assert "Collection Warnings" not in html
    assert "Collection:" not in html
    assert "Generated on:" in html
    assert "Source: matching evidence: 1 Webex, 0 Aha (0 ideas, 0 comments); 1 report entries after filtering likely asks and deduplicating exact repeats" in html
    assert "<code>evidence.json</code>" not in html
    assert '<h2 id="summary">Summary Table</h2>' in html
    assert '<a class="back-to-summary" href="#summary">Back to summary</a>' in html
    assert 'href="#alarm-and-event-delivery-coverage-as-an-operator-i-want-broader-alarm-and-event-coverage-through-webhooks-so-external-monitoring-systems-receive-the-events-i-care-about"' in html
    assert 'id="alarm-and-event-delivery-coverage-as-an-operator-i-want-broader-alarm-and-event-coverage-through-webhooks-so-external-monitoring-systems-receive-the-events-i-care-about"' in html
    assert f'href="webexteams://im?space={ROOM_UUID}&amp;message={MESSAGE_UUID}"' in html
    assert 'https://web.webex.com/spaces' not in html
    assert "<h4>1. Customer: person@example.com</h4>" not in html
    assert "Customer: person@example.com</li>" not in html
    assert f'<a href="webexteams://im?space={ROOM_UUID}&amp;message={MESSAGE_UUID}">Webex</a>' in html
    assert "Message API" not in html
    assert "webex-message-1" not in html
    assert "Related themes:" not in html


def test_html_falls_back_to_webex_space_link_when_message_id_missing():
    run = {
        "run_id": "webex-link-fallback",
        "warnings": [],
        "evidence": [{
            "id": "webex-message-1",
            "source": "webex",
            "source_type": "webex_message",
            "title": "Ask Intersight",
            "text": "Customer needs webhook delivery for alarms",
            "author": "person@example.com",
            "requester": "person@example.com",
            "created_at": "2026-01-01T00:00:00Z",
            "source_metadata": {
                "space_link": f"webexteams://im?space={ROOM_API_ID}",
                "room_id": ROOM_API_ID,
                "room_title": "Ask Intersight",
            },
        }],
    }
    html = build_report_html("webhooks", run)

    assert f'href="webexteams://im?space={ROOM_UUID}">Webex</a>' in html
    assert "message=" not in html


def test_webhook_report_dedupes_same_feedback_across_sources():
    feedback = "Please include service profile information, user label or tags in alarms sent through webhook."
    run = {
        "run_id": "combined",
        "warnings": [],
        "evidence": [
            {
                "id": "webex-message-1",
                "source": "webex",
                "source_type": "webex_message",
                "title": "Intersight Feedback",
                "text": f"New feedback was posted: Account Name: Intact Description: {feedback} Jira Id: ISFEEDBACK-603",
                "author": "bot@example.com",
                "requester": "bot@example.com",
                "created_at": "2026-01-14T16:13:20Z",
                "source_metadata": {"space_link": "webexteams://im?space=ROOM1", "room_title": "Intersight Feedback"},
            },
            {
                "id": "aha-idea-INI-I-804",
                "source": "aha",
                "source_type": "aha_idea",
                "title": "Include Service Profile and User Labels in Webhook Alarm Notifications",
                "text": {"body": feedback},
                "author": "",
                "requester": "Unknown",
                "created_at": "2026-03-30T17:35:49Z",
                "url": "https://example.aha.io/ideas/INI-I-804",
                "source_metadata": {"reference_num": "INI-I-804", "workflow_status": "Needs review", "idea_customers": ["INTACT INTERNATIONAL"]},
            },
        ],
    }
    report = build_report_skeleton("webhooks", run)
    assert "Source: matching evidence: 1 Webex, 1 Aha (1 ideas, 0 comments); 1 report entries after filtering likely asks and deduplicating exact repeats" in report
    assert "Raw feedback:" not in report
    assert "INTACT INTERNATIONAL" in report


def test_webhook_report_excludes_email_filter_feedback_that_only_mentions_webhooks():
    run = {
        "run_id": "aha",
        "warnings": [],
        "evidence": [{
            "id": "aha-idea-INI-I-793",
            "source": "aha",
            "source_type": "aha_idea",
            "title": "Allow UI configuration of advanced email notification filters",
            "text": {
                "body": (
                    "Allow UI configuration of advanced email notification filters. "
                    "Type: email. It would be easier to maintain if they had a UI option "
                    "to add the OData filters like we already have for webhooks and other screens."
                )
            },
            "author": "",
            "requester": "Unknown",
            "created_at": "2026-03-12T19:52:48Z",
            "url": "https://example.aha.io/ideas/INI-I-793",
            "source_metadata": {"reference_num": "INI-I-793", "workflow_status": "Needs review"},
        }],
    }
    report = build_report_skeleton("webhooks", run)
    assert "No Reportable Feedback Found" in report
    assert "advanced email notification filters" not in report


def test_aha_comments_are_not_primary_report_feedback():
    run = {
        "run_id": "aha-comments",
        "warnings": [],
        "evidence": [
            {
                "id": "aha-idea-INI-I-526",
                "source": "aha",
                "source_type": "aha_idea",
                "title": "Add profile name of affected object",
                "text": {"body": "Intersight webhook: please add profile name of the affected object in the json."},
                "author": "",
                "requester": "Example Customer",
                "created_at": "2024-08-14T15:25:22Z",
                "url": "https://example.aha.io/ideas/INI-I-526",
                "source_metadata": {"reference_num": "INI-I-526"},
            },
            {
                "id": "aha-comment-1",
                "source": "aha",
                "source_type": "aha_idea_comment",
                "title": "Comment on Add profile name of affected object",
                "text": "More info required from Customer. Question from Engineering Lead. Webhooks sends the contents of the object as is.",
                "author": "engineer@example.com",
                "requester": "Example Customer",
                "created_at": "2024-08-29T16:21:03Z",
                "url": "https://example.aha.io/ideas/INI-I-526",
                "source_metadata": {"idea_reference": "INI-I-526"},
            },
        ],
    }
    report = build_report_skeleton("webhooks", run)
    assert "Source: matching evidence: 0 Webex, 2 Aha (1 ideas, 1 comments); 1 report entries after filtering likely asks and deduplicating exact repeats" in report
    assert "Payload Fields and Object Context" in report
    assert "More info required from Customer" not in report


def test_aha_requester_uses_idea_customers_field():
    assert requester_from_idea({"idea_customers": [{"name": "Acme Corp"}]}) == "Acme Corp"
    assert requester_from_idea({"custom_fields": [{"name": "Idea Customers", "value": [{"name": "Globex"}]}]}) == "Globex"


def test_report_categories_sort_alphabetically_in_markdown_and_html():
    run = {
        "run_id": "sort",
        "warnings": [],
        "evidence": [
            {
                "id": "webex-1",
                "source": "webex",
                "source_type": "webex_message",
                "title": "Ask Intersight",
                "text": "Customer needs webhook delivery for alarms",
                "author": "a@example.com",
                "requester": "Customer A",
                "created_at": "2026-01-01T00:00:00Z",
                "source_metadata": {"room_title": "Ask Intersight"},
            },
            {
                "id": "webex-2",
                "source": "webex",
                "source_type": "webex_message",
                "title": "Ask Intersight",
                "text": "Customer needs webhook bearer token support",
                "author": "b@example.com",
                "requester": "Customer B",
                "created_at": "2026-01-02T00:00:00Z",
                "source_metadata": {"room_title": "Ask Intersight"},
            },
        ],
    }
    report = build_report_skeleton("webhooks", run)
    html = build_report_html("webhooks", run)
    assert report.index("| 1 | Alarm and Event Delivery Coverage |") < report.index("| 2 | Authentication and Authorization |")
    assert html.index("<td>Alarm and Event Delivery Coverage</td>") < html.index("<td>Authentication and Authorization</td>")


def test_category_hints_drive_combined_report_taxonomy():
    run = {
        "run_id": "taxonomy",
        "warnings": [],
        "evidence": [
            {
                "id": "aha-1",
                "source": "aha",
                "source_type": "aha_idea",
                "title": "Webhook teams",
                "text": "Customer needs webhook integration with Microsoft Teams",
                "requester": "Customer A",
                "created_at": "2026-01-01T00:00:00Z",
                "url": "https://example.aha.io/ideas/APP-I-1",
                "source_metadata": {"opportunity_value": "$1,000", "opportunity_value_numeric": 1000},
            },
            {
                "id": "aha-2",
                "source": "aha",
                "source_type": "aha_idea",
                "title": "Webhook payload",
                "text": "Customer needs webhook payload fields and profile name in JSON",
                "requester": "Customer B",
                "created_at": "2026-01-02T00:00:00Z",
                "url": "https://example.aha.io/ideas/APP-I-2",
                "source_metadata": {"opportunity_value": "$2,500", "opportunity_value_numeric": 2500},
            },
        ],
    }
    report = build_report_skeleton("webhooks", run)
    assert "## Integration Destinations, Payload Fields and Object Context" in report
    assert "## Integration Destinations\n" not in report
    assert "## Payload Fields and Object Context\n" not in report
    assert "| 1 | Integration Destinations, Payload Fields and Object Context |" in report
    assert "| 2 | Integration Destinations, Payload Fields and Object Context |" in report
    assert "$3,500 |" not in report
    assert "Microsoft Teams so teams that do not use Webex can receive notifications.](#integration-destinations-payload-fields-and-object-context-as-an-admin-i-want-webhook-integration-with-microsoft-teams-so-teams-that-do-not-use-webex-can-receive-notifications)" in report
    assert "payloads to include object names, labels, tags, and profile context so monitoring tools can act without extra lookups.](#integration-destinations-payload-fields-and-object-context-as-an-operator-i-want-webhook-payloads-to-include-object-names-labels-tags-and-profile-context-so-monitoring-tools-can-act-without-extra-lookups)" in report
    assert "| Customer A |" in report and "| $1,000 |" in report
    assert "| Customer B |" in report and "| $2,500 |" in report
    assert "Support webhook integration with Microsoft Teams." in report
    assert "Include webhook payload fields and profile name in JSON." in report
    assert "Improve webhook integration with named third-party tools and collaboration destinations." not in report
    assert "Include richer object context and fields directly in webhook payloads." not in report
    assert "Related themes:" not in report


def test_summary_rows_drill_into_matching_story_detail_sections():
    run = {
        "run_id": "story-drilldown",
        "warnings": [],
        "evidence": [
            {
                "id": "webex-teams",
                "source": "webex",
                "source_type": "webex_message",
                "title": "Ask Intersight",
                "text": "Customer needs webhook integration with Microsoft Teams",
                "requester": "Customer Teams",
                "created_at": "2026-01-01T00:00:00Z",
                "source_metadata": {"room_title": "Ask Intersight"},
            },
            {
                "id": "webex-payload",
                "source": "webex",
                "source_type": "webex_message",
                "title": "Ask Intersight",
                "text": "Customer needs webhook payload fields and profile name in JSON",
                "requester": "Customer Payload",
                "created_at": "2026-01-02T00:00:00Z",
                "source_metadata": {"room_title": "Ask Intersight"},
            },
        ],
    }
    report = build_report_skeleton("webhooks", run)

    teams_anchor = (
        "integration-destinations-payload-fields-and-object-context-as-an-admin-i-want-webhook-integration-with-"
        "microsoft-teams-so-teams-that-do-not-use-webex-can-receive-notifications"
    )
    payload_anchor = (
        "integration-destinations-payload-fields-and-object-context-as-an-operator-i-want-webhook-payloads-to-"
        "include-object-names-labels-tags-and-profile-context-so-monitoring-tools-can-act-without-extra-lookups"
    )
    assert f"](#{teams_anchor})" in report
    assert f"](#{payload_anchor})" in report
    assert f'<a id="{teams_anchor}"></a>' in report
    assert f'<a id="{payload_anchor}"></a>' in report

    teams_section = report.split(f'<a id="{teams_anchor}"></a>', 1)[1].split(f'<a id="{payload_anchor}"></a>', 1)[0]
    payload_section = report.split(f'<a id="{payload_anchor}"></a>', 1)[1]
    assert "Support webhook integration with Microsoft Teams." in teams_section
    assert "Include webhook payload fields and profile name in JSON." not in teams_section
    assert "Include webhook payload fields and profile name in JSON." in payload_section
    assert "Support webhook integration with Microsoft Teams." not in payload_section


def test_report_uses_actionable_table_and_customer_column():
    run = {
        "run_id": "layout",
        "warnings": [],
        "evidence": [
            {
                "id": "webex-1",
                "source": "webex",
                "source_type": "webex_message",
                "title": "Ask Intersight",
                "text": "Customer needs webhook delivery for alarms",
                "author": "a@example.com",
                "requester": "Customer A",
                "created_at": "2026-01-01T00:00:00Z",
                "source_metadata": {"room_title": "Ask Intersight"},
            },
            {
                "id": "webex-2",
                "source": "webex",
                "source_type": "webex_message",
                "title": "Ask Intersight",
                "text": "Customer wants webhook delivery for alarm events",
                "author": "b@example.com",
                "requester": "Customer B",
                "created_at": "2026-01-02T00:00:00Z",
                "source_metadata": {"room_title": "Ask Intersight"},
            },
        ],
    }
    report = build_report_skeleton("webhooks", run)
    assert "Feature ask:" not in report
    assert "| Customer / requester | Ask | Evidence | Opportunity Value |" in report
    assert "| Customer A |" in report
    assert "| Customer B |" in report
    assert "Support webhook delivery for alarms." in report
    assert "Support webhook delivery for alarm events." in report
    assert "Expand which alarms, events, and state changes can be delivered by webhook." not in report
    assert "#### 1. Customer: Customer A" not in report
    assert "#### 2. Customer: Customer B" not in report
    assert "- Customer: Customer A" not in report
    assert "- Customer: Customer B" not in report
    assert "| Not available |" in report


def test_report_uses_established_markdown_field_order():
    run = {
        "run_id": "shape",
        "warnings": [],
        "metadata": {
            "collection_profile": "accuracy",
            "status": "completed",
            "sources": {"webex": {"rooms_selected": 1, "rooms_available": 2}},
        },
        "evidence": [{
            "id": "webex-1",
            "source": "webex",
            "source_type": "webex_message",
            "title": "Ask Intersight",
            "text": "Customer needs webhook delivery for alarms",
            "requester": "Customer A",
            "created_at": "2026-01-01T00:00:00Z",
            "source_metadata": {
                "space_link": f"webexteams://im?space={ROOM_API_ID}",
                "room_id": ROOM_API_ID,
                "message_id": MESSAGE_API_ID,
                "room_title": "Ask Intersight",
            },
        }],
    }
    report = build_report_skeleton("webhooks", run)
    lines = report.splitlines()
    assert lines[0] == "# Webhook Feature Enhancement Feedback Report"
    assert lines[2].startswith("Generated on:")
    assert lines[3] == "Source: matching evidence: 1 Webex, 0 Aha (0 ideas, 0 comments); 1 report entries after filtering likely asks and deduplicating exact repeats"
    assert lines[4] == ""
    assert lines[5] == "## Summary Table"
    assert "Collection:" not in report
    assert "| Customer / requester | Ask | Evidence | Opportunity Value |" in report
    assert f'<a href="webexteams://im?space={ROOM_UUID}&message={MESSAGE_UUID}">Webex</a>' in report
    assert "Raw feedback:" not in report
    assert "Related themes:" not in report


def test_report_excludes_generic_and_repeated_actionable_asks():
    run = {
        "run_id": "specific-asks",
        "warnings": [],
        "evidence": [
            {
                "id": "webex-1",
                "source": "webex",
                "source_type": "webex_message",
                "title": "Ask Intersight",
                "text": (
                    "Customer needs API Getting Started documentation beyond authentication to include "
                    "API inventory/discovery, OpenAPI YAML/JSON, and Postman-style collections."
                ),
                "requester": "CX-CDA",
                "created_at": "2026-01-01T00:00:00Z",
                "source_metadata": {"room_title": "Ask Intersight"},
            },
            {
                "id": "webex-2",
                "source": "webex",
                "source_type": "webex_message",
                "title": "Ask Intersight",
                "text": "Customer reports an issue where the API Command Reference link for mo/BaseMos opens a blank page.",
                "requester": "STofTN-UCS-Lab",
                "created_at": "2026-01-02T00:00:00Z",
                "source_metadata": {"room_title": "Ask Intersight"},
            },
        ],
    }
    report = build_report_skeleton("intersight-apis", run)
    assert "Related themes:" not in report
    assert "Address API feedback:" not in report
    assert "Improve the accuracy, completeness, and navigability of Intersight API documentation." not in report
    assert "Expand API Getting Started documentation beyond authentication to include API inventory/discovery, OpenAPI YAML/JSON, and Postman-style collections." in report
    assert "Fix the API Command Reference link for mo/BaseMos opens a blank page." in report


def test_actionable_ask_rewrites_common_ungrammatical_fragments():
    examples = [
        (
            "Please consider adding a feature in Intersight that allows administrators to: "
            "Receive automated email notifications after each scheduled backup (Daily/Weekly).",
            "Alarm and Event Delivery Coverage",
            "Add automated email notifications after each scheduled backup.",
        ),
        (
            "Would it be possible to use webhook to be notified on Server Profile edit/apply/activate.",
            "Alarm and Event Delivery Coverage",
            "Add webhook notifications for Server Profile edit, Server Profile apply, and Server Profile activate events.",
        ),
        (
            "Webhook on Intersight CVA 1.0.9-675 and it's throwing 401 authentication error",
            "Authentication and Authorization",
            "Fix 401 authentication errors for webhooks on Intersight CVA 1.0.9-675.",
        ),
        (
            "We monitor our Intersight managed devices with these webhooks, and the disconnects are an issue for us.",
            "Delivery Reliability and Recovery",
            "Improve webhook connection reliability for monitoring Intersight-managed devices.",
        ),
    ]

    for raw, category, expected in examples:
        ask = build_actionable_ask(raw, category, "webhooks")
        assert ask == expected
        assert not ask.startswith(("Support consider", "Support possible", "Fix monitor", "Fix Webhook on"))


def test_actionable_ask_excludes_chatter_but_keeps_threaded_customer_feedback():
    excluded = [
        "Looks like a bug. I've filed CSC for the webhook issue.",
        "Correct, webhook is likely the first option.",
        "Please review the roadmap update for webhook work.",
        "testing bot webhooks - please ignore",
        "You can use webhooks to send alarms today.",
    ]
    for text in excluded:
        assert build_actionable_ask(text, "Alarm and Event Delivery Coverage", "webhooks") == ""

    threaded = (
        "Customer needs webhook integration with ServiceNow so incidents can be created automatically. "
        "Engineering replied that the current webhook can send generic payloads."
    )
    assert (
        build_actionable_ask(threaded, "Integration Destinations", "webhooks")
        == "Support webhook integration with ServiceNow so incidents can be created automatically."
    )


def test_actionable_ask_prefers_rich_customer_detail_over_weak_thread_leadin():
    pagerduty_message = (
        "Naresh Kumar K S\n"
        "Hi Subbu. we have customer issue with webhook.\n\n"
        "\"Customer is unable to integrate PagerDuty with Cisco Intersight CVA for their UCS Fabric Interconnect "
        "64108 (node: PNE-IT-CUCSD001+FI-A). The intended integration should allow automated alerting and "
        "incident management by sending notifications from Intersight to PagerDuty using the PagerDuty API, "
        "payload URL, and secret. However, every attempt to activate the integration results in a "
        "'Connection to host timed out' error, preventing successful alerting. This issue impacts the customer's "
        "ability to receive automated alerts for critical infrastructure events, potentially delaying incident "
        "response and affecting operational efficiency. The customer has confirmed that their enterprise proxy "
        "allows connections to other Cisco and Intersight sites, but HTTPS requests to pagerduty.com do not reach "
        "their proxy, suggesting the problem may be with Intersight's internal proxy or firewall configuration. \"\n"
        "Request coming rom our escalations team. Need support for proxy configuration for webhooks."
    )

    ask = build_actionable_ask(pagerduty_message, "CVA and Appliance Support", "webhooks")
    assert ask == "Support proxy configuration for CVA webhooks so Intersight can send PagerDuty notifications through the customer enterprise proxy."
    assert "we have customer issue" not in ask
    assert "Naresh" not in ask
    assert "Hi Subbu" not in ask
    assert "PagerDuty" in ask
    assert "CVA webhooks" in ask
    assert "proxy" in ask


def test_aha_collects_custom_object_idea_customers():
    class FakeAhaConnector(AhaConnector):
        def request_json(self, path, params=None):
            assert path == "/custom_object_records/record-1"
            return {
                "custom_object_record": {
                    "custom_fields": [
                        {"key": "customer_name", "name": "CAV Customer Name", "value": "INTACT INTERNATIONAL"}
                    ]
                }
            }

    connector = FakeAhaConnector()
    warnings = []
    customers = connector.collect_idea_customers(
        "INI-I-526",
        warnings,
        {"custom_object_links": [{"key": "customers_list", "name": "Idea Customers", "record_ids": ["record-1"]}]},
    )
    assert customers == ["INTACT INTERNATIONAL"]
    assert warnings == []
