from __future__ import annotations


def test_shared_auth_imports() -> None:
    import pm_assistant.auth.aha_auth
    import pm_assistant.auth.intersight_auth
    import pm_assistant.auth.jira_auth
    import pm_assistant.auth.snowflake_auth
    import pm_assistant.auth.webex_auth

    assert callable(pm_assistant.auth.jira_auth.auth_headers)

