-- Bronze/raw WheelReadingPurpose lookup extract: decodes LwrPurpose codes into the
-- SLAM website "Reason Of Turning" labels (flange/root/tread limit crossings, etc.).
SELECT
    WrpId,
    WrpName
FROM WheelReadingPurpose
ORDER BY WrpId;