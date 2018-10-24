use janice;

select cgm,bg,total_bolus_volume
from insulin_carb_smoothed
where corrective_insulin = 1;
