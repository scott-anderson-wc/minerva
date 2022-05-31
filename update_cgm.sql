SELECT date5f(coerce date as datetime) as rtime, mgdl
FROM realtime_cgm
WHERE date >= 2021-01-01;
