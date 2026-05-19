# Feature Feedback Report Format

Use this format when Codex writes `report.md` from collected raw evidence.

## Required Structure

1. H1 title from `title`.
2. `Generated on:` using the supplied generated timestamp.
3. `Source:` using the supplied source summary.
4. `## Summary Table` with columns:
   - #
   - Category
   - User story
   - Customers / requesters
   - Distinct customers / people
   - Opportunity Value Total
5. One detail section for every summary row.
6. Each summary `User story` cell must link to the matching detail section anchor.
7. Each detail section must start with an explicit HTML anchor:
   `<a id="..."></a>`
8. Each detail section contains a table with columns:
   - Customer / requester
   - Ask
   - Evidence
   - Opportunity Value

## Ask Quality

- The `Ask` must be written by reading the raw evidence.
- It must be accurate, grammatical, concise, and specific to the customer/requester feedback.
- It must not be a generic category summary.
- It must not quote or summarize support responses, confirmations, roadmap chatter, internal discussion, or solution guidance.
- If an evidence item does not contain a concrete customer/requester ask, exclude it.
- Exclude meeting summaries, action-item lists, deck/Jira/process updates, announcements, FYIs, internal review/funding/prioritization requests, and marketing/news content.
- Inspect nearby thread or room context when supplied. If the context says the ask is already available, shipped, fixed, resolved, answered, completed, no change required, or already supported, exclude it from open feedback.

## Evidence Links

- Evidence labels must be only `Webex` or `Aha`.
- Webex Markdown links must use the supplied decoded `webexteams://im?space=...&message=...` deep link.
- Aha Markdown links must use the supplied Aha URL.
- Do not use numbered source labels such as `Webex 01` or `Aha 01`.

## Opportunity Values

- Webex-only rows must show `Not available`.
- Aha rows use the exact opportunity value supplied for that evidence item.
- Summary totals sum only exact numeric Aha opportunity values in that summary group.
- Do not transfer opportunity values from one Aha idea to broader or related asks.

## Banned Output

Do not include:

- `Related themes:`
- `Address API feedback:`
- `Feature ask:`
- `Recommended Product Response`
- `Exclusions Applied`
- raw feedback fenced blocks
- collection warnings or diagnostics
