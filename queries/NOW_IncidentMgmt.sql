WITH servers_licenses AS (
    SELECT
        s.accountmoid, acs.cav_name as cav_name, acs.region,
        COUNT(DISTINCT s.serial) AS num_servers,
        SUM(CASE WHEN s.correct_license_tier ILIKE '%Base%' THEN 1 ELSE 0 END) AS base,
        SUM(CASE WHEN s.correct_license_tier ILIKE '%Essential%' THEN 1 ELSE 0 END) AS essentials,
        SUM(CASE WHEN s.correct_license_tier ILIKE '%Advantage%' THEN 1 ELSE 0 END) AS advantage,
        SUM(CASE WHEN s.correct_license_tier ILIKE '%Premier%' THEN 1 ELSE 0 END) AS premier,
        SUM(
            CASE
                WHEN s.correct_license_tier ILIKE '%Essential%'
                  OR s.correct_license_tier ILIKE '%Advantage%'
                  OR s.correct_license_tier ILIKE '%Premier%'
                THEN 1 ELSE 0
            END
        ) AS total_paid
    FROM engit_db.engit_isdatamart_br.servers s
    JOIN engit_db.engit_isdatamart_br.full_account_summary acs
        ON acs.accountmoid = s.accountmoid
    WHERE s.extraction_date = current_date()
      AND s.claimed_device = 'Claimed'
      AND acs.type_account NOT ILIKE '%INTERNAL%'
    GROUP BY s.accountmoid, acs.cav_name, acs.region
),

amer_accounts_plugins AS (
    SELECT
        apis.accountid,
        acs.top_hit_customer_domain AS customer_domain,
        apis.httpuseragent,
        MAX(apis.date_called) as last_call_date,
        CASE
            --WHEN apis.httpuseragent = 'ansible-httpget' THEN 'Ansible'
            WHEN apis.httpuseragent ILIKE 'OpenAPI/%-Incident/ServiceNow' THEN 'NOW Incident Management'
            --WHEN apis.httpuseragent ILIKE 'OpenAPI/SG-%/ServiceNow' THEN 'NOW Service Graph'
           -- WHEN apis.httpuseragent ILIKE 'OpenAPI/%/ServiceNow'
           --      AND apis.httpuseragent NOT ILIKE 'OpenAPI/SG-%/ServiceNow'
           --      AND apis.httpuseragent NOT ILIKE 'OpenAPI/%-Incident/ServiceNow'
           --     THEN 'NOW ITSM'
           -- WHEN apis.httpuseragent ILIKE 'ServiceNow/%' THEN 'NOW ITSM'
           -- WHEN apis.httpuseragent ILIKE 'Splunk_TA_Cisco_Intersight-%' THEN 'Splunk'
           -- WHEN apis.httpuseragent ILIKE '%/python%' THEN 'Python SDK'
           -- WHEN apis.httpuseragent ILIKE '%/terraform%' THEN 'Terraform'
           -- WHEN apis.httpuseragent ILIKE '%csharp%' THEN 'PowerShell'
           -- ELSE 'Other'
        END AS plugin
    FROM engit_db.engit_isdatamart_br.logstash_apicalls apis
    JOIN engit_db.engit_isdatamart_br.full_account_summary acs
        ON apis.accountid = acs.accountmoid
    WHERE acs.type_account NOT ILIKE '%INTERNAL%'
      AND apis.date_called >= current_date()-90
      AND (
           --apis.httpuseragent = 'ansible-httpget'
            --OR 
            apis.httpuseragent ILIKE 'OpenAPI/%-Incident/ServiceNow'
            --OR apis.httpuseragent ILIKE 'OpenAPI/SG-%/ServiceNow'
           -- OR apis.httpuseragent ILIKE 'OpenAPI/%/ServiceNow'
            --OR apis.httpuseragent ILIKE 'ServiceNow/%'
           -- OR apis.httpuseragent ILIKE 'Splunk_TA_Cisco_Intersight-%'
           -- OR apis.httpuseragent ILIKE '%/python%'
            --OR apis.httpuseragent ILIKE '%/terraform%'
           -- OR apis.httpuseragent ILIKE '%csharp%'
      )
    GROUP BY
        apis.accountid,
        acs.top_hit_customer_domain,
        plugin, apis.httpuseragent
),

emea_accounts_plugins AS (
    SELECT
        apis.accountid,
        acs.top_hit_customer_domain AS customer_domain,
        apis.httpuseragent,
        MAX(apis.date_called) as last_call_date,
        CASE
           --WHEN apis.httpuseragent = 'ansible-httpget' THEN 'Ansible'
            WHEN apis.httpuseragent ILIKE 'OpenAPI/%-Incident/ServiceNow' THEN 'NOW Incident Management'
            --WHEN apis.httpuseragent ILIKE 'OpenAPI/SG-%/ServiceNow' THEN 'NOW Service Graph'
           -- WHEN apis.httpuseragent ILIKE 'OpenAPI/%/ServiceNow'
           --      AND apis.httpuseragent NOT ILIKE 'OpenAPI/SG-%/ServiceNow'
           --      AND apis.httpuseragent NOT ILIKE 'OpenAPI/%-Incident/ServiceNow'
           --     THEN 'NOW ITSM'
           -- WHEN apis.httpuseragent ILIKE 'ServiceNow/%' THEN 'NOW ITSM'
           -- WHEN apis.httpuseragent ILIKE 'Splunk_TA_Cisco_Intersight-%' THEN 'Splunk'
           -- WHEN apis.httpuseragent ILIKE '%/python%' THEN 'Python SDK'
           -- WHEN apis.httpuseragent ILIKE '%/terraform%' THEN 'Terraform'
           -- WHEN apis.httpuseragent ILIKE '%csharp%' THEN 'PowerShell'
           -- ELSE 'Other'
        END AS plugin
    FROM engit_db.engit_isdatamart_br.emea_logstash_apicalls apis
    JOIN engit_db.engit_isdatamart_br.full_account_summary acs
        ON apis.accountid = acs.accountmoid
    WHERE acs.type_account NOT ILIKE '%INTERNAL%'
      AND apis.date_called >= current_date()-90
      AND (
            --apis.httpuseragent = 'ansible-httpget'
            --OR 
            apis.httpuseragent ILIKE 'OpenAPI/%-Incident/ServiceNow'
            --OR apis.httpuseragent ILIKE 'OpenAPI/SG-%/ServiceNow'
           -- OR apis.httpuseragent ILIKE 'OpenAPI/%/ServiceNow'
            --OR apis.httpuseragent ILIKE 'ServiceNow/%'
           -- OR apis.httpuseragent ILIKE 'Splunk_TA_Cisco_Intersight-%'
           -- OR apis.httpuseragent ILIKE '%/python%'
            --OR apis.httpuseragent ILIKE '%/terraform%'
           -- OR apis.httpuseragent ILIKE '%csharp%'
      )
    GROUP BY
        apis.accountid,
        acs.top_hit_customer_domain,
        plugin, apis.httpuseragent
),

amer_emea_accounts_plugins AS (
    SELECT * FROM amer_accounts_plugins
    UNION ALL
    SELECT * FROM emea_accounts_plugins
),

plugin_domain_stats AS (
    SELECT
        plugin,
        COUNT(DISTINCT customer_domain) AS num_of_customers
    FROM amer_emea_accounts_plugins
    GROUP BY plugin
)//,

//plugin_license_stats AS (

SELECT
    a.plugin,
    a.httpuseragent,
    sl.region,
    sl.accountmoid,
    sl.cav_name,
    MAX(a.last_call_date) AS last_call_date,
    SUM(sl.num_servers) AS num_servers,
    SUM(sl.base) AS base,
    SUM(sl.essentials) AS essentials,
    SUM(sl.advantage) AS advantage,
    SUM(sl.premier) AS premier,
    SUM(sl.total_paid) AS paid
FROM (
    SELECT
        accountid,
        plugin,
        httpuseragent,
        MAX(last_call_date) AS last_call_date
    FROM amer_emea_accounts_plugins
    GROUP BY accountid, plugin, httpuseragent
) a
JOIN servers_licenses sl
    ON sl.accountmoid = a.accountid
-- WHERE LOWER(sl.cav_name) ILIKE '%sinai%'
GROUP BY a.plugin, sl.region, sl.accountmoid, sl.cav_name, a.httpuseragent
Order BY sl.region, cav_name asc
//)