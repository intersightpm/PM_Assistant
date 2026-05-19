WITH non_internal_accounts AS (
    SELECT
        accountmoid,
        top_hit_customer_domain
    FROM engit_db.engit_isdatamart_br.full_account_summary
    WHERE type_account NOT ILIKE '%INTERNAL%'
      AND top_hit_customer_domain IS NOT NULL
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

classified_now_plugins AS (
    SELECT
        DATE_TRUNC('QUARTER', apis.date_called) AS calendar_qtr,
        acs.top_hit_customer_domain AS customer_domain,
        CASE
            WHEN apis.httpuseragent ILIKE 'OpenAPI/%-Incident/ServiceNow' THEN 'NOW Incident Management'
            WHEN apis.httpuseragent ILIKE 'OpenAPI/SG-%/ServiceNow' THEN 'NOW Service Graph'
            WHEN apis.httpuseragent ILIKE 'OpenAPI/%/ServiceNow'
                 AND apis.httpuseragent NOT ILIKE 'OpenAPI/SG-%/ServiceNow'
                 AND apis.httpuseragent NOT ILIKE 'OpenAPI/%-Incident/ServiceNow'
                THEN 'NOW ITSM'
            WHEN apis.httpuseragent ILIKE 'ServiceNow/%' THEN 'NOW ITSM'
        END AS plugin
    FROM all_api_calls apis
    JOIN non_internal_accounts acs
        ON apis.accountid = acs.accountmoid
    WHERE
        apis.httpuseragent ILIKE 'OpenAPI/%/ServiceNow'
        OR apis.httpuseragent ILIKE 'ServiceNow/%'
)

SELECT
    CONCAT(YEAR(calendar_qtr), 'Q', QUARTER(calendar_qtr)) AS "Qtr",
    COUNT(DISTINCT customer_domain) AS now_distinct_customers
FROM classified_now_plugins
WHERE plugin IN ('NOW ITSM', 'NOW Service Graph', 'NOW Incident Management')
GROUP BY calendar_qtr
ORDER BY calendar_qtr;
