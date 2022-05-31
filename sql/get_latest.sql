-- this gets the latest data (exactly one day) so we can throw it into
-- a spreadsheet for discussion

select rtime, cgm, bolus_type, total_bolus_volume, extended_bolus_amt_12, basal_amt_12, carbs
from insulin_carb_smoothed_2
where rtime > date_sub(now(), interval 1 day);
