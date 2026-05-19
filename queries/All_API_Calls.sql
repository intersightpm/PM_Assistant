select Date_Called, sum(Num_Calls) as Total_Calls
from (
select 'AMER', apis.date_called as Date_Called, sum(apis.num_calls) as Num_Calls 
from engit_db.engit_isdatamart_br.logstash_apicalls as apis LEFT OUTER JOIN engit_db.engit_isdatamart_br.account_summary as acs ON apis.accountid = acs.accountmoid 
where acs.type_account = 'External'and apis.date_called between current_date() - 180 and current_date()
group by apis.date_called 
//order by apis.date_called asc
UNION
select 'EMEA', emea_apis.date_called as Date_Called, sum(emea_apis.num_calls) as Num_Calls
from engit_db.engit_isdatamart_br.emea_logstash_apicalls as emea_apis LEFT OUTER JOIN engit_db.engit_isdatamart_br.emea_account_summary as emea_acs ON emea_apis.accountid = emea_acs.accountmoid 
where emea_acs.type_account = 'External'and emea_apis.date_called between current_date() - 180 and current_date()
group by emea_apis.date_called 
//order by emea_apis.date_called asc
) as all_calls
group by Date_Called
order by Date_Called asc