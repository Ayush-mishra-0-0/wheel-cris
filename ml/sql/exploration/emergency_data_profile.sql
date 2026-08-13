-- Inspect Emergency volume and transmission-time coverage before bulk extraction.
SELECT
    COUNT(*) AS TotalRows,
    MIN(EVENT_TRANSMISSION_TIME) AS MinTransmissionDate,
    MAX(EVENT_TRANSMISSION_TIME) AS MaxTransmissionDate
FROM INTEG_rtisLocoEmergencyData;
