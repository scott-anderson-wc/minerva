select max(rtime)
from insulin_carb_smoothed_2
where cgm is not null;

select count(*)
from insulin_carb_smoothed_2 as ics inner join realtime_cgm2 as rt using(rtime)
where rtime >= (select max(rtime) from insulin_carb_smoothed_2
                 where cgm is not null);

update insulin_carb_smoothed_2 as a inner join realtime_cgm2 as rt using (rtime)
set a.cgm = rt.mgdl
where rtime >= '2021-09-22 16:15:00';
