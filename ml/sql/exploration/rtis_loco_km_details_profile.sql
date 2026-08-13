-- Inspect RTIS volume and reporting-time coverage before any bulk extraction.
SELECT
    COUNT(*) AS TotalRows,
    MIN(RlkdReportDate) AS MinReportDate,
    MAX(RlkdReportDate) AS MaxReportDate
FROM RtisLocoKmDetails;
