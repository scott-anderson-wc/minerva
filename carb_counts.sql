select 'total carbs from original',sum(carbs) from insulin_carb_2;		 -- 188,289
select 'total carbs from smoothed',sum(carbs) from insulin_carb_smoothed;    -- 186,882

select 'missing carbs',a.carbsum-b.carbsum
from (
select sum(carbs) as carbsum from insulin_carb_2
) as a, (
select sum(carbs) as carbsum from insulin_carb_smoothed
) as b;

-- Not a lot of missing carbs

-- select year(date_time), month(date_time), sum(carbs)
-- from insulin_carb_2
-- group by year(date_time), month(date_time);

-- select year(rtime), month(rtime), sum(carbs)
-- from insulin_carb_smoothed
-- group by year(rtime), month(rtime);

drop function if exists yearmonth;
create function yearmonth (d timestamp)
returns char(7) deterministic
return date_format(d,'%Y-%m');

-- find discrepancies
select a.ym as 'year-mo', a.carbsum,b.carbsum,a.carbsum-b.carbsum as diff
from (
select yearmonth(date_time) as ym,sum(carbs) as carbsum from insulin_carb_2
group by yearmonth(date_time)
) as a, (
select yearmonth(rtime) as ym,sum(carbs) as carbsum from insulin_carb_smoothed
group by yearmonth(rtime)
) as b
where a.ym = b.ym
order by diff desc limit 10;

-- biggest month diff was 2015-06 with 234 missing carbs
-- here's the day-by-day difference.

select a.d as 'year-mo-da',a.carbsum,b.carbsum,a.carbsum-b.carbsum as diff
from (
select date(date_time) as d,sum(carbs) as carbsum
from insulin_carb_2
where date(date_time) like '2015-06-%'
group by date(date_time)
) as a, (
select date(rtime) as d,sum(carbs) as carbsum
from insulin_carb_smoothed
where date(rtime) like '2015-06-%'
group by date(rtime)
) as b
where a.d = b.d
order by diff desc
limit 10;

-- difference is worst for 2015-06-01: 334 versus 255 for 79 carbs in one day
-- let's zoom in even more

select 'original data for 2015-06-01';
select rec_num,date_time,carbs
from insulin_carb_2
where date(date_time) = '2015-06-01'
and carbs is not NULL and carbs > 0;

select 'smoothed data for 2015-06-01';
select rec_num,rtime,carbs
from insulin_carb_smoothed
where date(rtime) = '2015-06-01'
and carbs is not NULL and carbs > 0;

-- select a.rec_num,a.date_time,a.carbs,b.rec_num,b.rtime,b.carbs
-- from (
-- select rec_num,date_time,carbs
-- from insulin_carb_2
-- where date(date_time) = '2015-06-01'
-- and carbs is not NULL and carbs > 0
-- ) as a left outer join (
-- select rec_num,rtime,carbs
-- from insulin_carb_smoothed
-- where date(rtime) = '2015-06-01'
-- and carbs is not NULL and carbs > 0
-- ) as b on (a.rec_num = b.rec_num)
-- ;

-- select *
-- from insulin_carb_2 as a, insulin_carb_2 as b
-- where a.date_time < b.date_time and b.date_time < timestampadd(minute,10,a.date_time)
-- and a.carbs=b.carbs;

-- select a.rec_num, a.date_time, b.rec_num, b.date_time, a.carbs as carbs
-- from insulin_carb_2 as a, insulin_carb_2 as b
-- where a.rec_num = b.rec_num - 1
-- and a.carbs = b.carbs
-- order by a.rec_num, b.rec_num;

-- select sum(t.carbs) from (
-- select a.rec_num, a.date_time, a.carbs
-- from insulin_carb_2 as a, insulin_carb_2 as b
-- where a.rec_num = b.rec_num - 1
-- and a.carbs = b.carbs
-- ) as t;

-- date_time,carbs,a.rec_num

-- select count(*) 
-- from insulin_carb_2 as L left outer join insulin_carb_smoothed as R on (L.rec_num = R.rec_num)
-- where R.rec_num is NULL;

-- don't forget the NOT NULL part; otherwise the query fails!

# 22653
select 'count of records in original data',
count(*) from insulin_carb_2;

# 17379
select 'count of records from original data in the smoothed data',
count(*) from insulin_carb_smoothed where rec_num is not null;

# 5274
select 'count of records omitted in the smoothed data',
count(*) from insulin_carb_2 where rec_num not in (
    select rec_num from insulin_carb_smoothed where rec_num is not null
    );

# omitted records and the one after
-- select 'omitted records and the next record';
-- select rec_num,date_time,carbs from insulin_carb_2
-- where rec_num not in (
--     select rec_num from insulin_carb_smoothed where rec_num is not null
-- ) or rec_num - 1 not in (
--     select rec_num from insulin_carb_smoothed where rec_num is not null
-- );

drop view if exists samediff;
create view samediff as
select a.rec_num as arec, a.date_time as event_date_and_time, a.carbs as acarbs, b.rec_num as brec, timestampdiff(SECOND,a.date_time, b.date_time) as deltat, b.carbs as bcarbs, if(a.carbs is not null and b.carbs is not null and a.carbs = b.carbs, 'SAME', 'DIFF') as samediff
from (
select rec_num, date_time, carbs from insulin_carb_2
where rec_num not in (
    select rec_num from insulin_carb_smoothed where rec_num is not null
)) as a inner join (
select rec_num , date_time, carbs from insulin_carb_2
where rec_num - 1 not in (
    select rec_num from insulin_carb_smoothed where rec_num is not null
)) as b
on (a.rec_num = b.rec_num - 1)
where a.carbs is not NULL and b.carbs is not NULL;

select * from samediff;

select 'sum of all carb values',sum(acarbs),sum(bcarbs)
from samediff;

select 'sum of same carb values',sum(acarbs)
from samediff
where samediff='SAME';

-- SELECT a.rec_num as ar, a.date_time, a.carbs as acarbs, b.rec_num as br, timestampdiff(SECOND,a.date_time, b.date_time), b.carbs as bcarbs, if(a.carbs is not null and b.carbs is not null and a.carbs = b.carbs, 'SAME', 'DIFF') as samediff
-- from (
-- select rec_num, date_time, carbs from insulin_carb_2
-- where rec_num not in (
--     select rec_num from insulin_carb_smoothed where rec_num is not null
-- )) as a inner join (
-- select rec_num , date_time, carbs from insulin_carb_2
-- where rec_num - 1 not in (
--     select rec_num from insulin_carb_smoothed where rec_num is not null
-- )) as b
-- on (a.rec_num = b.rec_num - 1)
-- where a.carbs is not NULL and b.carbs is not NULL

-- ) as tab;

drop view if exists daily_diff;
create view daily_diff as
select ymd as yyyy_mm_dd, a.carbsum as acarbs, b.carbsum as bcarbs, a.carbsum-b.carbsum as diff
from (
select date(date_time) as ymd, sum(carbs) as carbsum
from insulin_carb_2
group by date(date_time)
) as a inner join (
select date(rtime) as ymd, sum(carbs) as carbsum
from insulin_carb_smoothed
group by date(rtime)
) as b using (ymd)
where (a.carbsum-b.carbsum) <> 0;

-- select * from daily_diff;

select 'sum of daily differences',sum(diff) from daily_diff;
