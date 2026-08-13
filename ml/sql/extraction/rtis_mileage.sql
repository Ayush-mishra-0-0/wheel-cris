-- Bronze/raw cohort-filtered RTIS mileage events.
-- Tokens are rendered by extract/extract.py from configs/experiment.yaml.
SELECT
    r.RlkdId,
    r.RlkdLocoNumber,
    r.RlkdReportDate,
    r.RlkdDivision,
    r.RlkdTotalDistance,
    r.RlkdSlamEntryDate
FROM RtisLocoKmDetails AS r
INNER JOIN LocoMaster AS lm
    ON lm.LomNumber = r.RlkdLocoNumber
INNER JOIN LocoTypes AS lt
    ON lt.LotId = lm.LomType
WHERE lt.LotTypeName = '{{COHORT}}'
  AND r.RlkdReportDate >= '{{START_DATE}}'
  AND r.RlkdReportDate < '{{END_DATE}}';
