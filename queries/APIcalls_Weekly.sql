SELECT 
    TO_DATE(
        DATEADD(day, - (DAYOFWEEK(Date_Called) - 1), Date_Called)
    ) AS Calendar_Week,
    SUM(Num_Calls) AS Total_Calls
FROM (
    SELECT 
        apis.date_called AS Date_Called, 
        SUM(apis.num_calls) AS Num_Calls 
    FROM engit_db.engit_isdatamart_br.logstash_apicalls AS apis 
    LEFT OUTER JOIN engit_db.engit_isdatamart_br.account_summary AS acs 
        ON apis.accountid = acs.accountmoid 
    WHERE acs.type_account = 'External'
        AND apis.date_called BETWEEN CURRENT_DATE() - 180 AND CURRENT_DATE()
    GROUP BY apis.date_called 

    UNION ALL

    SELECT 
        emea_apis.date_called AS Date_Called, 
        SUM(emea_apis.num_calls) AS Num_Calls
    FROM engit_db.engit_isdatamart_br.emea_logstash_apicalls AS emea_apis 
    LEFT OUTER JOIN engit_db.engit_isdatamart_br.emea_account_summary AS emea_acs 
        ON emea_apis.accountid = emea_acs.accountmoid 
    WHERE emea_acs.type_account = 'External'
        AND emea_apis.date_called BETWEEN CURRENT_DATE() - 180 AND CURRENT_DATE()
    GROUP BY emea_apis.date_called 
) AS all_calls
GROUP BY Calendar_Week
ORDER BY Calendar_Week ASC;