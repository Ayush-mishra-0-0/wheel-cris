-- Bronze/raw FunctionalLocations lookup extract: decodes LwrFuncLocId and employee
-- functional locations into shed names/codes (TKDE = Tughlakabad, AJJE = Arrakonam, etc.),
-- i.e. the "Measurement DoneAt" / HomeShed labels on the SLAM website.
SELECT
    FLocId,
    FLocName,
    FLocCode,
    FLocLocation,
    FLocFuncLocationType,
    flocDivId,
    flocConsigneeId
FROM FunctionalLocations
ORDER BY FLocId;