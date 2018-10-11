-- We first looked at duplicates of the cgm data, then the mgm data.
-- This is a check of the insulin_carb data.

-- ================================================================
-- finally, look at duplicates

select count(*) as 'duplicate insulin_carb timestamps'
from (select date_time
      from insulin_carb_2
      group by date_time
      having count(*) > 1) as T;

select count(*) as 'more than pairs'
from (select date_time
      from insulin_carb_2
      group by date_time
      having count(*) > 2) as T;

select date_time,count(*)
from insulin_carb_2
group by date_time
having count(*) > 2;

-- select date_time, basal_amt, bolus_type, bolus_volume, duration, carbs, notes from insulin_carb_2
-- where date_time in (select date_time from insulin_carb_2 group by date_time having count(*) > 1);
		    
