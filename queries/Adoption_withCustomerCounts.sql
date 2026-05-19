WITH domain_counts AS (
    SELECT
        COUNT(DISTINCT Customer_Domain) AS active_calling_domains
    FROM (
        SELECT
            Customer_Domain,
            SUM(total_calls) AS total_calls
        FROM (
            -- AMER region
            SELECT
                acs.top_hit_customer_domain AS Customer_Domain,
                SUM(apis.num_calls) AS total_calls
            FROM engit_db.engit_isdatamart_br.logstash_apicalls AS apis
            LEFT JOIN engit_db.engit_isdatamart_br.account_summary AS acs
                ON apis.accountid = acs.accountmoid
            WHERE acs.type_account = 'External'
              AND apis.date_called BETWEEN CURRENT_DATE() - 30 AND CURRENT_DATE() - 1
            GROUP BY acs.top_hit_customer_domain

            UNION ALL

            -- EMEA region
            SELECT
                emea_acs.top_hit_customer_domain AS Customer_Domain,
                SUM(emea_apis.num_calls) AS total_calls
            FROM engit_db.engit_isdatamart_br.emea_logstash_apicalls AS emea_apis
            LEFT JOIN engit_db.engit_isdatamart_br.emea_account_summary AS emea_acs
                ON emea_apis.accountid = emea_acs.accountmoid
            WHERE emea_acs.type_account = 'External'
              AND emea_apis.date_called BETWEEN CURRENT_DATE() - 30 AND CURRENT_DATE() - 1
            GROUP BY emea_acs.top_hit_customer_domain
        ) AS top_customers
        -- Aggregate AMER + EMEA before applying threshold
        GROUP BY Customer_Domain
    ) t
    WHERE total_calls > 1
      AND Customer_Domain IS NOT NULL
),
login_accounts AS (
    SELECT
        COUNT(*) AS active_logged_in_accounts
    FROM engit_db.engit_isdatamart_br.full_account_summary
    WHERE total_logins_90_days > 0
      AND type_account NOT ILIKE '%internal%'
)
SELECT
    d.active_calling_domains,
    l.active_logged_in_accounts,
    ROUND(
        d.active_calling_domains / NULLIF(l.active_logged_in_accounts, 0)::FLOAT * 100, 2
    ) AS adoption_rate_pct
FROM domain_counts d
CROSS JOIN login_accounts l;