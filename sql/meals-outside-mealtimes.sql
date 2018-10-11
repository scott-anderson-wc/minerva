-- It sometimes happens that we identify a meal (carbs and insulin
-- within +/- 30 minutes) that is after 9pm or before 6am. This query
-- identifies those

select count(*) from insulin_carb_smoothed where carb_code = 'before6' or carb_code = 'after9';

select rtime,carbs from insulin_carb_smoothed where carb_code = 'before6' or carb_code = 'after9';

select if(rtime=rtime_minus_30,'***','   ') as beginning,rtime,carbs,total_bolus_volume
from insulin_carb_smoothed as ICS,
     (select date_sub(rtime,interval 30 minute) as rtime_minus_30,
             date_add(rtime,interval 30 minute) as rtime_plus_30
      from insulin_carb_smoothed
      where carb_code = 'before6' or carb_code = 'after9') as T
where rtime >= rtime_minus_30 and rtime <= rtime_plus_30
order by rtime asc;
