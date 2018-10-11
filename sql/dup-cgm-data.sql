-- by reporting the min and max value, we can find out whether they are
-- duplicate rows or conflicting rows and by how much

select count(*) from
(select date_time, count(*), max(mgdl), min(mgdl) from cgm_2
group by date_time
having count(*) > 1) as t;

select date_time, count(*), max(mgdl), min(mgdl) from cgm_2
group by date_time
having count(*) > 1;

select '================================================================';
select 'the actual rows';

select IF(rec_num=G.min_rec_num,'***','   '),rec_num, date_time, mgdl
from cgm_2 inner join
(select date_time, min(rec_num) as min_rec_num from cgm_2 group by date_time having count(*) > 1) as G using (date_time);
