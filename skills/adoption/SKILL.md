# Adoption

Use this skill when a PM asks for usage, telemetry, adoption, trend, or segment analysis.

Workflow:
1. Use Snowflake MCP tools: `list_snowflake_queries`, `snowflake_query`, `run_snowflake_query_template`, or `prepare_adoption_summary`.
2. Record the data source, query/template name, date range, row count, and metric definitions.
3. Read `adoption-input://<run-id>` when prepared and `report-format://adoption_summary`.
4. Produce an adoption summary with trends, segment notes, risks, and recommended PM actions.

Use "Not available" for missing metrics. Do not infer adoption from feedback volume alone.
