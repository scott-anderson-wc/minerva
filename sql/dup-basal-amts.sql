select date_time,basal_amt,rec_num
from insulin_carb_2
where date_time in (
    select date_time
    from insulin_carb_2
    group by date_time
    having count(*) > 1 and min(basal_amt) < max(basal_amt));
    
