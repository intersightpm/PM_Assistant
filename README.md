# PM Assistant

PM Assistant is an MCP-powered toolkit that helps Codex Desktop act as a product manager's assistant. It connects Codex to PM data sources, collects evidence, and supports repeatable workflows for feedback scans, PRD drafting, desk research, Jira updates, and data analysis.

Codex is the agent/runtime. PM Assistant provides the tools, connectors, auth helpers, prompts, skills, and artifact templates.

## What It Can Do

- Connect to Webex, Aha, Jira, Snowflake and Intersight
- Collect and search feedback from Aha, Webex, and Jira.
- Prepare raw evidence for Codex-authored feedback reports.
- Query Snowflake (read-only)  - it can run pre-built queries or generate new ones.
- Draft PRDs from customer evidence and optional cited research.
- Read/Update  Jira.
- Store local run artifacts under `runs/<run-id>/`. 

## Install

```powershell
git clone https://github.com/intersightpm/PM_Assistant
cd PM_Assistant
python -m pip install -r requirements.txt
python -m pip install -e .
pm-assistant doctor --sources aha,jira,webex,snowflake
```

If `pm-assistant` is not on PATH:

```powershell
python -m pm_assistant.cli doctor --sources aha,jira,webex,snowflake
```


## Credentials Setup

Do not commit credentials, `.env`, service env files, raw runs, or customer data.

Each PM should create their own local env files from templates:
You can configure the keys for each tool in the respective '.env' files

```powershell
Copy-Item env_examples\aha.env.example aha.env
Copy-Item env_examples\webex.env.example webex.env
Copy-Item env_examples\jira.env.example jira.env
Copy-Item env_examples\snowflake.env.example snowflake.env
Copy-Item env_examples\intersight-us.env.example intersight-us.env
Copy-Item env_examples\intersight-eu.env.example intersight-eu.env
```

Fill only the services you plan to use.

Authentication lookup order:

1. Project-local `.env` and `<service>.env`
2. Optional central secrets directory: `C:\Users\<you>\.codex\secrets\`
3. Existing process environment variables

Advanced users can override the central secret path:

```powershell
$env:CODEX_AUTH_SECRETS_DIR = "C:\path\to\secrets"
```


## PM Assistant MCP Setup in Codex

Add this to your Codex Desktop config, adjusting the path:

```toml
[mcp_servers.pm_assistant]
command = "python"
args = ["-m", "pm_assistant.mcp_server"]
cwd = "C:\\path\\to\\PM_Assistant"
enabled = true
```

Restart Codex or reload tools.

Quick Codex Desktop tests:

```text
List available PM Assistant tools.
Use PM Assistant to run doctor for jira, aha, webex, and snowflake.
Use PM Assistant to run Intersight doctor for all accounts.
```

## How PMs Use It

Plain English works for flexible tasks:

```text
Analyze feedback for webhooks from Aha, Webex, and Jira. Generate a feedback report.
```

```text
Write a PRD for dense GPU server management using recent customer feedback.
```

Skills make workflows more repeatable:

```text
@feedback-scan API
@prd dense GPU server management
@jira-update ABC-123
@research webhook proxy support
@adoption advisories
```

MCP tools are usually invisible to the PM. Codex calls them to collect evidence, read resources, prepare inputs, validate artifacts, and optionally update Jira.

## CLI Examples

```powershell
pm-assistant collect --topic "webhooks" --sources aha,webex,jira
pm-assistant search --query "proxy support" --run-id <run-id>
pm-assistant prepare-report --topic "webhooks" --run-id <run-id>
pm-assistant prepare-prd --topic "webhooks" --run-id <run-id>
pm-assistant validate-prd --run-id <run-id>
pm-assistant snowflake-templates
pm-assistant collect-adoption --topic "server management" --sources snowflake,intersight --save
pm-assistant intersight-doctor --account all
pm-assistant intersight-count --account all --object-type compute/PhysicalSummaries
pm-assistant intersight-get --account us --path /api/v1/iam/Accounts
pm-assistant mcp
```


## GitHub Publish Checklist

- Confirm `python -m pytest -q` passes.
- Confirm `runs/`, `.env`, service env files, private keys, and caches are not present.
- Publish only `env_examples/`, never real credentials.
- Ask teammates to configure their own local tokens and private keys.
- Ask teammates to add the `[mcp_servers.pm_assistant]` block to their own Codex Desktop config.

## Extending Connectors

New third-party apps should follow the connector pattern:

- `doctor()`
- `collect(topic_config, date_range=None)`
- optional safe read/search/update methods

Future connector candidates include Fullstory, Whatfix, Figma etc.

## Safety

- `runs/` can contain customer evidence and is ignored by git.
- Jira write tools should be used only after an explicit user request.
- External research should be saved as a separate research packet and cited by URL.
