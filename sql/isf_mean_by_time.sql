-- the complete set of ISF values is a mess. So, this reports just the mean of each group
-- I'd rather use the median, but I think the mean will be okay.

select time,avg(isf) as mean_isf, count(isf) as n
from (select 60*hour(rtime)+minute(rtime) as time, isf from isf_details) as t
group by time
order by time;
