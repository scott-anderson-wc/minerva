-- searching the original food_diary would require regexp, and even that
-- is fragile

-- This is close to our desired date range (2-digit dates in April and
-- 1-digit dates in May).


select real_date,item1,item2,item3,item4,item5,item6,item7,item8,item9 from food_diary
where meal = 'dinner'
  and (real_date regexp '4/[[:digit:]]+/2016'
   or  real_date regexp '5/[[:digit:]]/2016');

-- here's a duplicate

select real_date,item1,item2,item3,item4,item5,item6,item7,item8,item9 from food_diary
where meal = 'dinner' and real_date = '4/24/2016'\G

-- This uses the food_diary_2 table, which is simpler and omits duplicates:

select date as 'FD2 dinners' from food_diary_2
where date BETWEEN cast('2016-04-02' as date) and cast('2016-05-02' as date)
and meal = 'dinner';

-- ================================================================
-- Would something like this work?
-- yields 3 matches. Yes, it seems to work!

select * from food_diary_2
where date BETWEEN cast('2016-04-02' as date) and cast('2016-05-02' as date)
and meal = 'dinner'
and (item1 like '%avocado%' or
     item2 like '%avocado%' or
     item3 like '%avocado%' or
     item4 like '%avocado%' or
     item5 like '%avocado%' or
     item6 like '%avocado%' or
     item7 like '%avocado%' or
     item8 like '%avocado%' or
     item9 like '%avocado%');
     
-- So much bogus data, though. Here are is a date with two meals and 40 data values

select rtime, cgm, carb_code, carbs, minutes_since_last_meal
from insulin_carb_smoothed_2
where date(rtime) = '2016-04-09'
      and rtime >= '2016-04-09 18:10:00';
      
