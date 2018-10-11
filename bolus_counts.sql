select sum(bolus_volume) from insulin_carb_2;  # 13779.62
select sum(bolus_volume) from insulin_carb_smoothed;  # 13728.42

# difference of 51.20 over the four years

select a.ym,round(a.bv),round(b.bv)
from (
select concat(year(date_time),'-',month(date_time)) as ym ,sum(bolus_volume) as bv
from insulin_carb_2 group by ym) as a,
(select concat(year(rtime),'-',month(rtime)) as ym ,sum(bolus_volume) as bv
from insulin_carb_smoothed group by ym) as b
where a.ym = b.ym;

# biggest diff was 2015-6 (409 vs 393)

select a.d,a.bv,b.bv
from (

select day(date_time) as d, sum(bolus_volume) as bv
from insulin_carb_2
where date_format(date_time, '%Y-%m') = '2015-06'
group by day(date_time)

) as a,(

select day(rtime) as d, sum(bolus_volume) as bv
from insulin_carb_smoothed
where date_format(rtime, '%Y-%m') = '2015-06'
group by day(rtime)

) as b
where a.d = b.d;

# biggest difference is on 2015-06-01 (18.5 versus 13.9)

select date_time, bolus_volume
from insulin_carb_2
where date(date_time) = '2015-06-01' and bolus_volume > 0;

select rtime, bolus_volume
from insulin_carb_smoothed
where date(rtime) = '2015-06-01' and bolus_volume > 0;

# the difference is a sole entry of 4.65 at 8:10 and 8:12
# the smoothed version eliminated the duplicate













