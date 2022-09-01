-- stats for the past week
-- we use 8 because today's data will always be incomplete

select date(rtime), count(*) as 'rows', min(mgdl) as 'min', round(avg(mgdl)) as 'avg', max(mgdl) as 'max'
from realtime_cgm2
where datediff(current_date(), rtime) < 8
group by date(rtime);

select date(rtime), count(*) as 'real', if(count(*)=288,'FULL',288-count(*)) as 'missing'
from realtime_cgm2
where datediff(current_date(), rtime) < 8
  and mgdl is not null
group by date(rtime);
