/*
===============================================================================
RTIS SEMANTICS SAMPLE RECORDS
===============================================================================
*/

WITH base AS (

    SELECT
        r.RlkdId,
        r.RlkdLocoNumber AS loco_number,
        TRY_CAST(r.RlkdReportDate AS date) AS report_date,
        r.RlkdDivision AS division,
        TRY_CAST(r.RlkdTotalDistance AS decimal(18,3)) AS distance_value
    FROM RtisLocoKmDetails r
    INNER JOIN LocoMaster lm
        ON CAST(lm.LomNumber AS varchar(20))
         = CAST(r.RlkdLocoNumber AS varchar(20))
    INNER JOIN LocoTypes lt
        ON lt.LotId=lm.LomType
    WHERE lt.LotTypeName='WAP7'
      AND TRY_CAST(r.RlkdReportDate AS date)
          BETWEEN '2023-02-06' AND '2026-07-28'
),

daily AS (

    SELECT
        loco_number,
        report_date,
        MAX(distance_value) AS daily_max_value
    FROM base
    GROUP BY
        loco_number,
        report_date

),

seq AS (

    SELECT
        *,
        LAG(daily_max_value)
            OVER(PARTITION BY loco_number ORDER BY report_date)
            AS previous_max
    FROM daily

)

SELECT TOP (50)

    loco_number,

    report_date,

    previous_max,

    daily_max_value,

    CASE

        WHEN daily_max_value>previous_max
            THEN 'INCREASE'

        WHEN daily_max_value<previous_max
            THEN 'DECREASE'

        ELSE 'EQUAL'

    END AS behaviour

FROM seq

WHERE previous_max IS NOT NULL

ORDER BY
    loco_number,
    report_date;