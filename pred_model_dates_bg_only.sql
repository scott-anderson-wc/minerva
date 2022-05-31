-- lots of dynamic_insulin and bg values are null. Let's find dates where we can try our predictive model
-- this file only looks at BG, not BG and CGM which works better. Look at that.

select date(rtime),count(*) as n
from insulin_carb_smoothed_2
where dynamic_insulin is not null
and bg is not null
group by date(rtime)
order by n desc
limit 10;

create temporary table good_dates (rtime date);

insert into good_dates 
select date(rtime)
from insulin_carb_smoothed_2
where dynamic_insulin is not null
and bg is not null
group by date(rtime)
having count(*)=21;

select * from good_dates;

select rtime,bg,dynamic_insulin
from insulin_carb_smoothed_2
where date(rtime) in (select * from good_dates);




