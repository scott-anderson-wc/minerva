-- because the carb absorption curves are 3 hours long, it will almost certainly happen that
-- the three-hour period after one meal will overlap another meal.  Let's see:

select A.rtime, A.carb_code, B.rtime, B.carb_code
from insulin_carb_smoothed A, insulin_carb_smoothed B
where date_add(A.rtime,interval 3 hour) < B.rtime
and A.carb_code <> B.carb_code;

