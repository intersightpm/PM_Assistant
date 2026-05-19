WITH non_internal_accounts AS (
    SELECT
        accountmoid,
        top_hit_customer_domain
    FROM engit_db.engit_isdatamart_br.full_account_summary
    WHERE type_account NOT ILIKE '%INTERNAL%'
      AND top_hit_customer_domain IS NOT NULL
),

api_accounts_qtr AS (
    SELECT DISTINCT
        accountid,
        DATE_TRUNC('QUARTER', date_called) AS calendar_qtr
    FROM engit_db.engit_isdatamart_br.logstash_apicalls
    WHERE date_called >= '2025-01-01'

    UNION

    SELECT DISTINCT
        accountid,
        DATE_TRUNC('QUARTER', date_called) AS calendar_qtr
    FROM engit_db.engit_isdatamart_br.emea_logstash_apicalls
    WHERE date_called >= '2025-01-01'
),

api_customers_qtr AS (
    SELECT DISTINCT
        a.accountid,
        a.calendar_qtr,
        n.top_hit_customer_domain
    FROM api_accounts_qtr a
    JOIN non_internal_accounts n
        ON a.accountid = n.accountmoid
),

server_license_flags AS (
    SELECT
        s.accountmoid,
        DATE_TRUNC('QUARTER', s.extraction_date) AS calendar_qtr,
        MAX(IFF(s.correct_license_tier ILIKE '%Advantage%', 1, 0)) AS has_advantage,
        MAX(IFF(s.correct_license_tier ILIKE '%Essential%', 1, 0)) AS has_essential
    FROM engit_db.engit_isdatamart_br.servers s
    JOIN (
        SELECT DISTINCT accountid, calendar_qtr
        FROM api_customers_qtr
    ) a
        ON a.accountid = s.accountmoid
       AND a.calendar_qtr = DATE_TRUNC('QUARTER', s.extraction_date)
    WHERE s.claimed_device = 'Claimed'
      AND s.extraction_date >= '2025-01-01'
      AND (
          s.correct_license_tier ILIKE '%Advantage%'
          OR s.correct_license_tier ILIKE '%Essential%'
      )
    GROUP BY
        s.accountmoid,
        DATE_TRUNC('QUARTER', s.extraction_date)
),

customer_license_flags AS (
    SELECT
        a.calendar_qtr,
        a.top_hit_customer_domain,
        MAX(COALESCE(s.has_advantage, 0)) AS has_advantage,
        MAX(COALESCE(s.has_essential, 0)) AS has_essential
    FROM api_customers_qtr a
    LEFT JOIN server_license_flags s
        ON s.accountmoid = a.accountid
       AND s.calendar_qtr = a.calendar_qtr
    GROUP BY
        a.calendar_qtr,
        a.top_hit_customer_domain
)

SELECT
    CONCAT(YEAR(calendar_qtr), 'Q', QUARTER(calendar_qtr)) AS qtr,
    COUNT(DISTINCT top_hit_customer_domain) AS api_customers,

    COUNT(DISTINCT CASE
        WHEN has_advantage = 1 THEN top_hit_customer_domain
    END) AS advantage_customers_using_apis,

    COUNT(DISTINCT CASE
        WHEN has_advantage = 0
         AND has_essential = 1 THEN top_hit_customer_domain
    END) AS essentials_only_customers_using_apis

FROM customer_license_flags
GROUP BY calendar_qtr
ORDER BY calendar_qtr;