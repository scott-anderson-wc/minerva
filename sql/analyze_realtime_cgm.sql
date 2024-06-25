-- first, let's see whether all the timestamps are proper rtime values

-- select minute(rtime),count(*) from realtime_cgm2 group by minute(rtime);

-- yes. they are.

-- How many "flat" areas are there (no change for 60 minutes)

-- First, group by latest rtime
select min(mgdl), max(mgdl), rtime


select rtime from realtime_cgm2
where 1 < 
       -- subquery returns number of recent rows with matching mgdl
    (select count(*) as num from realtime_cgm2 as t2
    where (t2.rtime between subtime(rtime, "1:00:00") and rtime)
    and   (mgdl = t2.mgdl)
    );
    

