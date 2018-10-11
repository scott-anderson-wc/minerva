select rtime,date_time,basal_amt,rec_num
from insulin_carb_2
where rtime in (
    select rtime
    from insulin_carb_2
    group by rtime
    having count(*) > 1 and min(basal_amt) < max(basal_amt));
    
