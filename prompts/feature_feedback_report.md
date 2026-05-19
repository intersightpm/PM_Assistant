# Feature Feedback Report Instructions

Use this template when Codex is asked to analyze customer feedback for a feature.

## Ground Rules

- Use only collected evidence from the selected run.
- Do not invent customers, request counts, dates, links, product claims, or asks.
- Preserve source traceability for every report entry.
- Link every report entry to its original Webex message or Aha idea.
- If evidence is weak or sparse, say so clearly.
- Treat Python-generated candidates as raw evidence only. Codex is responsible for deciding which items are reportable.
- Inspect raw Webex/Aha text and any `source_context` before including a row.

## Evidence Review Rubric

Include evidence only when it is a real customer/requester ask, pain point, product gap, or enhancement request about the requested feature, and the provided context does not show that it is already resolved.

Exclude evidence when it is:

- internal team chatter, engineering discussion, roadmap debate, FYI, announcement, or marketing/news content;
- meeting summaries, action-item lists, deck edits, Jira/process updates, scheduling, or project management tasks;
- support answers, confirmations, workaround guidance, troubleshooting responses, or links shared only as an answer;
- an item later shown in the same context as available, shipped, fixed, resolved, answered, completed, no change required, or already supported;
- a request for internal review, feedback, prioritization, funding, or approval rather than customer product feedback.

## Required Markdown Shape

1. H1 title: `{Feature Name} Feature Enhancement Feedback Report` unless the feature profile overrides it.
2. `Generated on:` timestamp in Pacific time and source run summary.
3. Summary table with these columns:
   - #
   - Category
   - User story
   - Customers / requesters
   - Distinct customers / people
   - Opportunity Value Total
4. Category sections sorted alphabetically by category.
5. Under each category, include one actionable feedback table with:
   - Customer / requester
   - Actionable ask
   - Evidence
   - Opportunity Value
   The `Actionable ask` must describe the exact enhancement requested in that row's evidence. Do not repeat category summaries as row-level asks, and do not use repeated generic wording across rows.
   Do not include rows merely because they matched keywords; include only rows that survive the evidence review rubric.
6. Each evidence cell must use source-only link labels:
   - `Webex` linking to the original `webexteams://im?...&message=...` deep link.
   - `Aha` linking to the original Aha idea URL.
7. Opportunity values must be scoped to source evidence:
   - Webex-only rows use `Not available`.
   - Aha rows use the Aha opportunity value when present.
   - Summary totals sum only Aha numeric opportunity values in that category.

Do not include `Story NN`, `Feature ask:`, `Related themes:`, raw feedback fenced blocks, `Recommended Product Response`, `Exclusions Applied`, or generic fallback asks such as `Address API feedback:` in user-facing reports. Keep raw evidence, sender, search text, Aha ref, status, and score in evidence metadata/run artifacts rather than the displayed report.

Do not include collection diagnostics, collection metadata, or a `Collection Warnings` section in user-facing reports. Keep warnings and collection metadata in run artifacts and tool responses.

## Feature Profiles

When a feature-specific profile exists in `configs/`, use that profile for categories, request filters, summaries, and user-story wording. Treat `category_hints` as the preferred report taxonomy first, then merge matching detailed category rules underneath those hinted names. Append additional useful categories only when they are not covered by the hints. When no feature profile exists, use the generic report shape above and derive categories only from the collected evidence.
