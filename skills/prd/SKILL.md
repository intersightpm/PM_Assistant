# PRD

Use this skill when a PM asks to write, draft, or update a PRD for a topic/product area.

Workflow:
1. Collect or reuse internal evidence with `collect_pm_evidence`.
2. If the user asks for market/competitor context, do cited desk research and save it with `save_research_packet`.
3. Call `prepare_prd_input(topic, run_id, research_run_id?)`.
4. Read `prd-input://<run-id>` and `report-format://prd`.
5. Write `runs/<run-id>/prd.md`.
6. Call `validate_prd` and fix validation failures.

Keep internal customer evidence separate from external research. Use "Not available" rather than inventing metrics or dates.
