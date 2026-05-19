SELECT
        s.accountmoid, acs.cav_name, acs.region,
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
    order by acs.region, acs.cav_name asc