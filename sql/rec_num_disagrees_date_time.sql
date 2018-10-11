select A.rec_num,B.rec_num,A.date_time,B.date_time
from insulin_carb_2 A, insulin_carb_2 B
where A.rec_num < B.rec_num and A.date_time > B.date_time;
