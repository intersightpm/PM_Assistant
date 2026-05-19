WITH non_internal_accounts AS (
    SELECT
        accountmoid,
        top_hit_customer_domain
    FROM engit_db.engit_isdatamart_br.full_account_summary
    WHERE type_account NOT ILIKE '%INTERNAL%'
),

all_api_calls AS (
    SELECT accountid, date_called, httpuseragent
    FROM engit_db.engit_isdatamart_br.logstash_apicalls
    WHERE date_called >= '2025-01-01'

    UNION ALL

    SELECT accountid, date_called, httpuseragent
    FROM engit_db.engit_isdatamart_br.emea_logstash_apicalls
    WHERE date_called >= '2025-01-01'
),

classified_plugins AS (
    SELECT
        apis.accountid,
        DATE_TRUNC('QUARTER', apis.date_called) AS calendar_qtr,
        acs.top_hit_customer_domain AS customer_domain,
        CASE
            WHEN apis.httpuseragent = 'ansible-httpget' THEN 'Ansible'
            WHEN apis.httpuseragent ILIKE 'OpenAPI/%-Incident/ServiceNow' THEN 'NOW Incident Management'
            WHEN apis.httpuseragent ILIKE 'OpenAPI/SG-%/ServiceNow' THEN 'NOW Service Graph'
            WHEN apis.httpuseragent ILIKE 'OpenAPI/%/ServiceNow'
                 AND apis.httpuseragent NOT ILIKE 'OpenAPI/SG-%/ServiceNow'
                 AND apis.httpuseragent NOT ILIKE 'OpenAPI/%-Incident/ServiceNow'
                THEN 'NOW ITSM'
            WHEN apis.httpuseragent ILIKE 'ServiceNow/%' THEN 'NOW ITSM'
            WHEN apis.httpuseragent ILIKE 'Splunk_TA_Cisco_Intersight-%' THEN 'Splunk'
            WHEN apis.httpuseragent ILIKE '%/python%' THEN 'Python SDK'
            WHEN apis.httpuseragent ILIKE '%/terraform%' THEN 'Terraform'
            WHEN apis.httpuseragent ILIKE '%csharp%' THEN 'PowerShell'
        END AS plugin
    FROM all_api_calls apis
    JOIN non_internal_accounts acs
        ON apis.accountid = acs.accountmoid
    WHERE
        apis.httpuseragent = 'ansible-httpget'
        OR apis.httpuseragent ILIKE 'OpenAPI/%/ServiceNow'
        OR apis.httpuseragent ILIKE 'ServiceNow/%'
        OR apis.httpuseragent ILIKE 'Splunk_TA_Cisco_Intersight-%'
        OR apis.httpuseragent ILIKE '%/python%'
        OR apis.httpuseragent ILIKE '%/terraform%'
        OR apis.httpuseragent ILIKE '%csharp%'
),

account_plugin_qtr AS (
    SELECT DISTINCT
        accountid,
        calendar_qtr,
        plugin
    FROM classified_plugins
    WHERE plugin IS NOT NULL
),

domain_plugin_qtr AS (
    SELECT DISTINCT
        calendar_qtr,
        plugin,
        customer_domain
    FROM classified_plugins
    WHERE plugin IS NOT NULL
      AND customer_domain IS NOT NULL
),

plugin_account_qtr AS (
    SELECT DISTINCT
        accountid,
        calendar_qtr
    FROM account_plugin_qtr
),

server_qtr_max AS (
    SELECT
        s.accountmoid,
        p.calendar_qtr,
        MAX(s.extraction_date) AS max_extraction_date
    FROM engit_db.engit_isdatamart_br.servers s
    JOIN plugin_account_qtr p
        ON p.accountid = s.accountmoid
       AND p.calendar_qtr = DATE_TRUNC('QUARTER', s.extraction_date)
    WHERE s.claimed_device = 'Claimed'
      AND s.extraction_date >= '2025-01-01'
    GROUP BY
        s.accountmoid,
        p.calendar_qtr
),

servers_licenses AS (
    SELECT
        s.accountmoid,
        m.calendar_qtr,
        COUNT(DISTINCT s.serial) AS num_servers,
        SUM(IFF(s.correct_license_tier ILIKE '%Base%', 1, 0)) AS base,
        SUM(IFF(s.correct_license_tier ILIKE '%Essential%', 1, 0)) AS essentials,
        SUM(IFF(s.correct_license_tier ILIKE '%Advantage%', 1, 0)) AS advantage,
        SUM(IFF(s.correct_license_tier ILIKE '%Premier%', 1, 0)) AS premier,
        SUM(IFF(
            s.correct_license_tier ILIKE '%Essential%'
            OR s.correct_license_tier ILIKE '%Advantage%'
            OR s.correct_license_tier ILIKE '%Premier%',
            1, 0
        )) AS total_paid
    FROM engit_db.engit_isdatamart_br.servers s
    JOIN server_qtr_max m
        ON m.accountmoid = s.accountmoid
       AND m.max_extraction_date = s.extraction_date
    WHERE s.claimed_device = 'Claimed'
      AND s.extraction_date >= '2025-01-01'
    GROUP BY
        s.accountmoid,
        m.calendar_qtr
),

plugin_domain_stats AS (
    SELECT
        calendar_qtr,
        plugin,
        COUNT(*) AS num_of_customers
    FROM domain_plugin_qtr
    GROUP BY
        calendar_qtr,
        plugin
),

plugin_license_stats AS (
    SELECT
        a.calendar_qtr,
        a.plugin,
        SUM(sl.num_servers) AS num_servers,
        SUM(sl.base) AS base,
        SUM(sl.essentials) AS essentials,
        SUM(sl.advantage) AS advantage,
        SUM(sl.premier) AS premier,
        SUM(sl.total_paid) AS paid
    FROM account_plugin_qtr a
    LEFT JOIN servers_licenses sl
        ON sl.accountmoid = a.accountid
       AND sl.calendar_qtr = a.calendar_qtr
    GROUP BY
        a.calendar_qtr,
        a.plugin
)

SELECT
    CONCAT(YEAR(pds.calendar_qtr), 'Q', QUARTER(pds.calendar_qtr)) as "Qtr",
    -- pds.calendar_qtr,
    pds.plugin,
    pds.num_of_customers,
    COALESCE(pls.essentials, 0) AS essentials,
    COALESCE(pls.advantage, 0) AS advantage
FROM plugin_domain_stats pds
LEFT JOIN plugin_license_stats pls
    ON pds.calendar_qtr = pls.calendar_qtr
   AND pds.plugin = pls.plugin
ORDER BY
    pds.calendar_qtr,
    pds.plugin;