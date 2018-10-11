-- We first looked at duplicates of the cgm data, then the mgm data.
-- This is a check of the insulin_carb data.

-- This script only reads the data.

select count(*) as 'total insulin_carb records'
from insulin_carb_2;

select count(*) as 'nonempty temp_basal_down'
from (select date_time
      from insulin_carb_2
      where temp_basal_down is not null and
            temp_basal_down <> '') as T;
	    
select count(*) as 'nonempty temp_basal_up'
from (select date_time
      from insulin_carb_2
      where temp_basal_up is not null and
            temp_basal_up <> '') as T;

select count(*) as 'nonempty temp_basal_duration'
from (select date_time
      from insulin_carb_2
      where temp_basal_duration is not null and
            temp_basal_duration <> '') as T;

select count(*) as 'bolus_types'
from (select distinct(bolus_type) from insulin_carb_2) as T;

select lpad(bolus_type,15,' ') as 'bolus type',count(*)
from insulin_carb_2
group by bolus_type;

select count(*) as 'nonempty Immediate_percent'
from (select date_time
      from insulin_carb_2
      where Immediate_percent is not null and
            Immediate_percent <> '') as T;

select count(*) as 'nonempty extended_percent'
from (select date_time
      from insulin_carb_2
      where extended_percent is not null and
            extended_percent <> '') as T;

select count(*) as 'nonempty duration'
from (select date_time
      from insulin_carb_2
      where duration is not null and
            duration <> '') as T;

select cast(duration as unsigned),count(*)
from insulin_carb_2
group by duration
order by cast(duration as unsigned);

select notes,count(*)
from insulin_carb_2
group by notes;


-- so, all the interesting fields are
-- date_time, basal_amt, bolus_type, bolus_volume, duration, carbs, notes

-- Now, what's up with bolus_type and bolus_volume? The output of the
-- following shows that bolus_type is '' when bolus_volume is NULL
-- (originally ''). Then, *most* of the time, bolus_type is in
-- {Normal,Combination} and bolus_volume > 0, but sometimes we have a
-- zero bolus_volume with a bolus_type.

select bolus_type,bolus_volume=0,count(*)
from insulin_carb_2
group by bolus_type,bolus_volume = 0;

-- Sometimes, more than one insulin event happens at one time. There are 169 such:

select count(*) as 'multiple insulin events at one time' from (
select date_time,count(*)
from insulin_carb_2
where bolus_type <> ''
group by date_time
having count(*) > 1
) as T;

select count(*) as 'multiple Normal insulin events at one time' from (
select date_time,count(*)
from insulin_carb_2
where bolus_type = 'Normal'
group by date_time
having count(*) > 1
) as T;

select count(*) as 'multiple Combination insulin events at one time' from (
select date_time,count(*)
from insulin_carb_2
where bolus_type = 'Combination'
group by date_time
having count(*) > 1
) as T;
     
select count(*) as 'two different insulin types at one time' from (
select date_time,count(*)
from insulin_carb_2
where bolus_type <> ''
group by date_time
having count(*) > 1 and  min(bolus_type) = 'Combination'  and max(bolus_type) = 'Normal'
) as T;
     
