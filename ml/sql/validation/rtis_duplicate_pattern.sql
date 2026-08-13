/*
===============================================================================
RTIS DUPLICATE BUSINESS REPORTS
===============================================================================
*/

WITH duplicate_groups AS (

    SELECT

        RlkdLocoNumber,

        TRY_CAST(RlkdReportDate AS date) AS report_date,

        RlkdDivision,

        TRY_CAST(RlkdTotalDistance AS decimal(18,3)) AS distance_value,

        COUNT(*) AS report_count,

        MIN(RlkdId) AS first_id,

        MAX(RlkdId) AS last_id

    FROM RtisLocoKmDetails

    GROUP BY

        RlkdLocoNumber,

        TRY_CAST(RlkdReportDate AS date),

        RlkdDivision,

        TRY_CAST(RlkdTotalDistance AS decimal(18,3))

    HAVING COUNT(*)>1

)

SELECT TOP (200)

    dg.RlkdLocoNumber,

    dg.report_date,

    dg.RlkdDivision,

    dg.distance_value,

    dg.report_count,

    r.RlkdId,

    r.RlkdSlamEntryDate

FROM duplicate_groups dg

INNER JOIN RtisLocoKmDetails r

ON dg.RlkdLocoNumber=r.RlkdLocoNumber

AND dg.report_date=
    TRY_CAST(r.RlkdReportDate AS date)

AND dg.RlkdDivision=r.RlkdDivision

AND dg.distance_value=
    TRY_CAST(r.RlkdTotalDistance AS decimal(18,3))

ORDER BY

    dg.report_count DESC,

    dg.RlkdLocoNumber,

    dg.report_date,

    r.RlkdSlamEntryDate;