# Jira Update

Use this skill when a PM asks to summarize, comment on, or update a Jira issue with customer/product context.

Workflow:
1. Read the issue with `jira_read_issue` or prepare context with `prepare_jira_update`.
2. If evidence context is needed, search or collect PM evidence first.
3. Read `report-format://jira_update`.
4. Draft a concise Jira-ready update.
5. Only call `jira_add_comment` after the user explicitly asks to post the comment.

Do not transition issues, delete data, or edit fields unless a future MCP tool explicitly supports that safe operation.
