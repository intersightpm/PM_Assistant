import json

from pm_assistant.core.pm_workflows import prepare_prd_input, save_research_packet, validate_prd


def test_prepare_prd_input_preserves_feedback_and_research(tmp_path):
    run_dir = tmp_path / "topic-run"
    run_dir.mkdir()
    (run_dir / "evidence.json").write_text(json.dumps({
        "run_id": "topic-run",
        "feature_name": "webhooks",
        "evidence": [{
            "id": "jira-1",
            "source": "jira",
            "source_type": "jira_issue",
            "title": "Webhook proxy support",
            "text": "Customer needs proxy support for webhook delivery.",
            "requester": "Customer A",
            "url": "https://example.atlassian.net/browse/ABC-1",
        }],
    }), encoding="utf-8")
    research = save_research_packet(
        "webhooks",
        [{"summary": "Proxy support is common for enterprise integrations."}],
        citations=[{"url": "https://example.com/research", "title": "Research"}],
        run_id="research-run",
        runs_dir=tmp_path,
    )

    package = prepare_prd_input("webhooks", "topic-run", research_run_id=research["run_id"], runs_dir=tmp_path)

    assert package["artifact_type"] == "prd"
    assert package["feedback"]["evidence_items"][0]["raw_evidence"] == "Customer needs proxy support for webhook delivery."
    assert package["research"]["citations"][0]["url"] == "https://example.com/research"
    assert (run_dir / "prd_input.json").exists()


def test_validate_prd_requires_core_sections_and_citation(tmp_path):
    run_dir = tmp_path / "topic-run"
    run_dir.mkdir()
    (run_dir / "prd.md").write_text(
        "\n".join([
            "# Webhooks PRD",
            "## Problem",
            "## Evidence",
            "https://example.com/evidence",
            "## Goals",
            "## Non-goals",
            "## Requirements",
            "## Success Metrics",
            "## Open Questions",
        ]),
        encoding="utf-8",
    )

    assert validate_prd("topic-run", runs_dir=tmp_path)["ok"]
