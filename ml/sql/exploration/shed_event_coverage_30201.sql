SELECT shed_source, COUNT_BIG(*) AS records,
       MIN(shed_start) AS earliest_shed_start,
       MAX(shed_end) AS latest_shed_end
FROM (
    SELECT 'foisshedin' AS shed_source, EntryDateTime AS shed_start,
           COALESCE(OutDateTime, EntryDateTime) AS shed_end
    FROM foisshedin WHERE LocoNumber = '30201'
    UNION ALL
    SELECT 'foisshedout', ShedStartTime,
           COALESCE(ShedEndtime, OutDateTime, ShedStartTime)
    FROM foisshedout WHERE LocoNumber = '30201'
) AS events
GROUP BY shed_source;
