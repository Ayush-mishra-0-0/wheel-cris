-- Bronze/raw COA schedule extract: shed assignment and schedule-due context per
-- loco number. Cohort-filtered via LocoMaster.
SELECT
    s.IntgFLid,
    s.LOCONUM,
    lm.LomId AS LocoId,
    s.LOCOSHED,
    s.GEOSHED,
    s.SHEDSTRTTIME,
    s.SHEDENDTIME,
    s.SHEDOUTDATE,
    s.CURRSCHDCODE,
    s.CURRSCHDDUEDATE,
    s.CURRSCHDMNDTFLAG,
    s.CURRSCHDDAYS,
    s.CURRSCHDVRTNDAYS,
    s.NEXTSCHDCODE,
    s.NEXTSCHDDUEDATE,
    s.NEXTSCHDMNDTFLAG,
    s.NEXTSCHDDAYS,
    s.NEXTSCHDVRTNDAYS,
    s.NEXTBASESCHDCODE,
    s.NEXTBASESCHDDATE,
    s.NEXTBASESCHDMNDTFLAG,
    s.NEXTBASESCHDDURNDAYS,
    s.NEXTBASESCHDVRTNDAYS,
    s.NEXTICSCHDDUEDATE,
    s.NEXTAOHSCHDDUEDATE,
    s.NEXTIOHSCHDDUEDATE,
    s.NEXTPOHSCHDDUEDATE,
    s.OutRMRK,
    s.SlamDateTime
FROM Integ_pub_COA_slamlocoSchedule AS s
INNER JOIN LocoMaster AS lm
    ON lm.LomNumber = s.LOCONUM
INNER JOIN LocoTypes AS lt
    ON lt.LotId = lm.LomType
WHERE lt.LotTypeName = '{{COHORT}}';
