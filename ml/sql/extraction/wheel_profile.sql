-- Bronze/raw WheelProfile lookup extract: decodes LwrWheelProfile codes into
-- wheel-profile class names (1 = Thick Flange, 2 = Wear Adapted).
SELECT
    WpID AS WpId,
    WpWheelProfileName
FROM WheelProfile
ORDER BY WpID;