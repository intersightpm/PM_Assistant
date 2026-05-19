WITH params AS (
    SELECT
        TO_DATE(DATEADD(day, -DAYOFWEEK(CURRENT_DATE()), CURRENT_DATE())) AS current_week_start,
        TO_DATE(CURRENT_DATE() - 180) AS raw_start_date
),
bounds AS (
    SELECT
        current_week_start,
        TO_DATE(DATEADD(day, -DAYOFWEEK(raw_start_date), raw_start_date)) AS raw_start_week_start,
        raw_start_date
    FROM params
),
final_bounds AS (
    SELECT
        current_week_start,
        CASE
            WHEN raw_start_date = raw_start_week_start THEN raw_start_date
            ELSE DATEADD(day, 7, raw_start_week_start)
        END AS window_start_date
    FROM bounds
),
weekly_totals AS (
    SELECT 
        TO_DATE(DATEADD(day, -DAYOFWEEK(Date_Called), Date_Called)) AS Calendar_Week,
        SUM(Num_Calls) AS Total_Calls
    FROM (
        SELECT 
            TO_DATE(apis.date_called) AS Date_Called, 
            SUM(apis.num_calls) AS Num_Calls 
        FROM engit_db.engit_isdatamart_br.logstash_apicalls AS apis 
        LEFT OUTER JOIN engit_db.engit_isdatamart_br.account_summary AS acs 
            ON apis.accountid = acs.accountmoid 
        WHERE acs.type_account = 'External'
        GROUP BY TO_DATE(apis.date_called)

        UNION ALL

        SELECT 
            TO_DATE(emea_apis.date_called) AS Date_Called, 
            SUM(emea_apis.num_calls) AS Num_Calls
        FROM engit_db.engit_isdatamart_br.emea_logstash_apicalls AS emea_apis 
        LEFT OUTER JOIN engit_db.engit_isdatamart_br.emea_account_summary AS emea_acs 
            ON emea_apis.accountid = emea_acs.accountmoid 
        WHERE emea_acs.type_account = 'External'
        GROUP BY TO_DATE(emea_apis.date_called)
    ) AS all_calls
    CROSS JOIN final_bounds b
    WHERE Date_Called >= b.window_start_date
      AND Date_Called <  b.current_week_start
    GROUP BY Calendar_Week
)
SELECT
    AVG(Total_Calls)::FLOAT AS Weekly_Avg_API_Calls
FROM weekly_totals;