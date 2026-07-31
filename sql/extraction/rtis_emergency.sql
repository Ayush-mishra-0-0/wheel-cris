-- Bronze/raw cohort-filtered RTIS emergency events.
-- Preserve source strings and timestamps; interpret event codes in Silver.
SELECT
    e.IrledId,
    e.LOCO_NO,
    e.DEVICE_ID,
    e.COMM_TYPE,
    e.EVENT_TYPE,
    e.MSG_DESC,
    e.EVENT_TIME,
    e.KILOMETERAGE,
    e.SHORT_MSG_CODE,
    e.LATITUDE,
    e.LONGITUDE,
    e.SPEED,
    e.EVENT_TRANSMISSION_TIME,
    e.SEQUENCE_NUMBER,
    e.STTN_CODE,
    e.DVSN_LIST,
    e.NEAR_STTN_DIST,
    e.RECV_DATETIME
FROM INTEG_rtisLocoEmergencyData AS e
INNER JOIN LocoMaster AS lm
    ON lm.LomNumber = e.LOCO_NO
INNER JOIN LocoTypes AS lt
    ON lt.LotId = lm.LomType
WHERE lt.LotTypeName = '{{COHORT}}'
  AND e.EVENT_TRANSMISSION_TIME >= '{{START_DATE}}'
  AND e.EVENT_TRANSMISSION_TIME < '{{END_DATE}}';
