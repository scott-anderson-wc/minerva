-- How often do we get good ISF values? How many per week/month?

select 'counts by bucket';
select time_bucket(rtime),count(isf)
from isf_details
group by time_bucket(rtime);

select 'counts by bucket from 2014';
select time_bucket(rtime),count(isf)
from isf_details
where year(rtime)=2014
group by time_bucket(rtime);

-- select year(rtime),week(rtime),count(isf)
-- from isf_details
-- group by year(rtime),week(rtime)
-- order by year(rtime),week(rtime);

select '================================================================';
select 'year(rtime),quarter(rtime),time_bucket(rtime),count(isf) as n';

select year(rtime) as 'yyyy', quarter(rtime) as 'qq' ,time_bucket(rtime) as 'tb', count(isf) as n
from isf_details inner join ics using (rtime)
group by year(rtime),quarter(rtime),time_bucket(rtime);

select '================================================================';
select 'stats per quarter';

select avg(n) as 'avg',
       min(n) as 'min',
       max(n) as 'max'
from (
select year(rtime),quarter(rtime),time_bucket(rtime),count(isf) as n
from isf_details inner join ics using (rtime)
group by year(rtime),quarter(rtime),time_bucket(rtime)
) as t;



