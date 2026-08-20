-- Bronze/raw ScheduleTypes lookup extract: decodes LwrScheduleId into schedule
-- code/name (UnSch, IA, IC, TI, IB, IOH, POH, M-series, RM-series, periodic, etc.).
SELECT
    SctId,
    SctCode,
    SctName,
    SctKind,
    SctDuration,
    SctLevel,
    SctDays,
    SctLocoType
FROM ScheduleTypes
ORDER BY SctId;