-- Inspect the FOIS event table before deciding on an extraction window.
SELECT
    COUNT(*) AS TotalRows,
    MIN(FOISrptgtime) AS MinReportDate,
    MAX(FOISrptgtime) AS MaxReportDate
FROM FOIS_LocoLocation_History;
