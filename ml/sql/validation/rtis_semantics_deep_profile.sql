/*
===============================================================================
RTIS SEMANTICS DEEP PROFILE
Purpose:
Characterize the behaviour of RlkdTotalDistance.
This script DOES NOT infer travelled kilometres.
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
        ON lt.LotId = lm.LomType
    WHERE lt.LotTypeName='WAP7'
      AND TRY_CAST(r.RlkdReportDate AS date)
          BETWEEN '2023-02-06' AND '2026-07-28'
),

daily AS (

    SELECT
        loco_number,
        report_date,

        COUNT_BIG(*) AS row_count,

        COUNT(DISTINCT division) AS division_count,

        MIN(distance_value) AS daily_min_value,

        MAX(distance_value) AS daily_max_value

    FROM base

    GROUP BY
        loco_number,
        report_date

),

sequenced AS (

    SELECT
        *,
        LAG(report_date) OVER
            (PARTITION BY loco_number ORDER BY report_date)
            AS previous_date,

        LAG(daily_max_value) OVER
            (PARTITION BY loco_number ORDER BY report_date)
            AS previous_daily_max

    FROM daily

),

duplicate_keys AS (

    SELECT
        loco_number,
        report_date,
        division,
        distance_value

    FROM base

    GROUP BY
        loco_number,
        report_date,
        division,
        distance_value

    HAVING COUNT(*)>1

)

SELECT
    'source_rows' AS metric,
    CAST(COUNT_BIG(*) AS decimal(19,2)) AS value
FROM base

UNION ALL

SELECT
    'loco_day_rows',
    CAST(COUNT_BIG(*) AS decimal(19,2))
FROM daily

UNION ALL

SELECT
    'loco_days_multiple_divisions',
    CAST(COUNT_BIG(*) AS decimal(19,2))
FROM daily
WHERE division_count>1

UNION ALL

SELECT
    'duplicate_business_keys',
    CAST(COUNT_BIG(*) AS decimal(19,2))
FROM duplicate_keys

UNION ALL

SELECT
    'positive_daily_max_changes',
    CAST(COUNT_BIG(*) AS decimal(19,2))
FROM sequenced
WHERE previous_daily_max IS NOT NULL
  AND daily_max_value>previous_daily_max

UNION ALL

SELECT
    'negative_daily_max_changes',
    CAST(COUNT_BIG(*) AS decimal(19,2))
FROM sequenced
WHERE previous_daily_max IS NOT NULL
  AND daily_max_value<previous_daily_max

UNION ALL

SELECT
    'equal_daily_max_changes',
    CAST(COUNT_BIG(*) AS decimal(19,2))
FROM sequenced
WHERE previous_daily_max=daily_max_value

UNION ALL

SELECT
    'gaps_over_one_day',
    CAST(COUNT_BIG(*) AS decimal(19,2))
FROM sequenced
WHERE DATEDIFF(day,previous_date,report_date)>1

UNION ALL

SELECT
    'maximum_gap_days',
    CAST(MAX(DATEDIFF(day,previous_date,report_date)) AS decimal(19,2))
FROM sequenced
WHERE previous_date IS NOT NULL;