# Feedback Scan

Use this skill when a PM asks for top feedback themes, product gaps, customer asks, or unresolved pain points for a topic.

Workflow:
1. If no run id is provided, call `collect_pm_evidence(topic, sources, date_range?, config?)`.
2. Read `evidence://<run-id>` and `report-format://feature_feedback`.
3. Call `prepare_report_input(topic, run_id)`.
4. Review raw evidence semantically. Exclude internal chatter, resolved/shipped items, support answers, and unrelated matches.
5. Produce a concise feedback scan or write `runs/<run-id>/report.md` when the user asks for an artifact.
6. If writing a report, call `validate_report` and `render_report_html`.

Do not invent customers, counts, opportunity value, dates, or evidence links.
