SELECT TOP (100)
    f.IntgFLid, f.LocoNumb, lt.LotTypeName AS LocoType, f.RTISEvnttime,
    f.FOISrptgtime, f.RTISLatd, f.RTISLngt, f.RTISSttn, f.RTISDvsn,
    f.FOISSttn, f.FOISDvsn, f.RecordCreatedTimestamp
FROM INTEG_FOIS_LocoLocation AS f
LEFT JOIN LocoMaster AS l ON f.LocoNumb = l.LomNumber
LEFT JOIN LocoTypes AS lt ON lt.LotId = l.LomType
ORDER BY f.RTISEvnttime DESC, f.IntgFLid DESC;
