# PM Assistant Routing

This repository provides PM Assistant, a Codex MCP toolkit for product-management workflows. When working in this repo, use the `pm_assistant` MCP server by default for PM-related requests.

Use PM Assistant when the user asks about:

- feedback analysis
- product gaps or customer themes
- PRDs or requirements drafts
- Jira issue summaries, comments, or update drafts
- adoption metrics
- Snowflake usage data
- Intersight inventory, health, adoption, troubleshooting, or impact analysis
- product-area research or evidence synthesis

Treat topics like Webhooks, APIs, GPU servers, licensing, and adoption as topic context, not separate tools or separate repos.

Do not require the user to say "Use PM Assistant" when the task is clearly PM-related. Map natural-language PM requests to the available PM Assistant MCP tools and prompts.

Keep source access and artifact generation GitHub-safe:

- never commit credentials, `.env` files, private keys, raw customer data, or generated `runs/` output
- use files under `env_examples/` as templates only
- prefer read-only source operations unless the user explicitly asks for a write action
- draft Jira updates before writing them unless the user explicitly approves the write
