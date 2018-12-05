use janice;

-- select isf,isf_rounded from insulin_carb_smoothed_2
-- where isf is not null and isf_rounded is not null;

-- select count(*) as non_null_isf
-- from insulin_carb_smoothed_2
-- where isf is not null;

-- select count(*) as non_null_isfr
-- from insulin_carb_smoothed_2
-- where isf_rounded is not null;

drop function if exists time_bucket;
create function  time_bucket( d datetime )
returns  integer  deterministic
return 2*floor(hour(d)/2);

drop table if exists isfvals;
create table isfvals (
       rtime datetime,
       isf   float
       );

insert into isfvals
select rtime,isf from insulin_carb_smoothed_2
       where isf is not null
       union  
       select rtime,isf_rounded as isf from insulin_carb_smoothed_2
       where isf_rounded is not null;

select time_bucket(rtime),count(isf)
from isfvals
group by time_bucket(rtime);

