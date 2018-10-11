select * from
       (select week(rtime),sum(carbs),sum(dynamic_carbs), sum(carbs) - sum(dynamic_carbs) as diff
       from insulin_carb_smoothed
       where year(rtime)=2017
       group by week(rtime)) as T
order by diff desc;

       
select min(rtime),max(rtime)
from insulin_carb_smoothed
where year(rtime)=2017 and week(rtime) = 29;

select date(rtime),sum(carbs),sum(dynamic_carbs),sum(carbs) - sum(dynamic_carbs) as diff
from insulin_carb_smoothed
where year(rtime)=2017 and week(rtime) = 29
group by date(rtime);

select 'off by a lot: ',date(rtime),sum(carbs),sum(dynamic_carbs),sum(carbs) - sum(dynamic_carbs) as diff
from insulin_carb_smoothed
where date(rtime) = '2017-07-21';

# the details

select rtime,carbs,dynamic_carbs
from insulin_carb_smoothed
where date(rtime) = '2017-07-21';

# the following is normal

select 'breakfast is fine',sum(carbs),sum(dynamic_carbs)
from insulin_carb_smoothed
where date(rtime) = '2017-07-21' and time(rtime) >= '07:35:00' and time(rtime) <= '10:35:00';

select * 
from insulin_carb_smoothed
where date(rtime) = '2017-07-21' and time(rtime) = '21:25:00';

select week,Asum,Bsum,Asum-Bsum   as diff from
    (select week(rtime) as week, sum(carbs) as Asum, sum(dynamic_carbs) as Bsum
     from insulin_carb_smoothed
     where year(rtime)=2017
     group by week(rtime)) as A
order by diff desc;

select Aweek,Asum,Bsum,Asum-Bsum as diff from
       (select week(rtime) as Aweek, sum(carbs) as Asum
       from insulin_carb_smoothed
       where year(rtime)=2017
       group by week(rtime)) as A,
       (select week(rtime) as Bweek, sum(dynamic_carbs) as Bsum
       from insulin_carb_smoothed
       where year(rtime)=2017
       group by week(rtime)) as B
where  Aweek = Bweek
order by diff desc;

# both of the preceding queries show week 29 to be off by a lot, namely 252 carbs.

select Aweek,Asum,Bsum,Asum-Bsum as diff from
       (select week(rtime) as Aweek, sum(carbs) as Asum
       from insulin_carb_smoothed
       where year(rtime)=2017 and carb_code in ('breakfast','lunch','snack','dinner','rescue')
       group by week(rtime)) as A,
       (select week(rtime) as Bweek, sum(dynamic_carbs) as Bsum
       from insulin_carb_smoothed
       where year(rtime)=2017
       group by week(rtime)) as B
where  Aweek = Bweek
order by diff desc;

-- the preceding shows negligible differences, so the trouble is definitely the outside meals.

-- I thought I'd fixed the problem, but I guess not.

select carb_code,sum(carbs)
from insulin_carb_smoothed
where year(rtime) = 2017 and week(rtime) = 29
group by carb_code;

-- The difference is almost certainly the after9 carbs, because the
-- preceding query shows there are 252 carbs labeled after9, which is
-- the difference.


-- You can ignore the rest of this file

# Week 46 in 2017 is off by a lot, namely 213 carbs; is it the outside meals?


select 'sum all',sum(carbs)
from insulin_carb_smoothed
where year(rtime) = 2017 and week(rtime) = 29;
select 'sum meals',sum(carbs)
from insulin_carb_smoothed
where year(rtime) = 2017 and week(rtime) = 29
and carb_code in ('breakfast','lunch','snack','dinner','rescue');
select 'sum outside',sum(carbs)
from insulin_carb_smoothed
where year(rtime) = 2017 and week(rtime) = 29
and carb_code in ('before6','after9')
select 'sum dc',sum(dynamic_carbs)
from insulin_carb_smoothed
where year(rtime) = 2017 and week(rtime) = 29;

-- The preceding for week 46 showed dc sum is 1613, which is the sum
-- all, which I did not expect. In other words, its as if the dynamic
-- carbs *does* include the outside meals

-- for week 29, we get 1170 total carbs, 749 from normal meals and 421 from outside meals, but dc totals 917

select rtime,carb_code,carbs
from insulin_carb_smoothed
where year(rtime)=2017 and week(rtime)=29 and carb_code not in  ('breakfast','lunch','snack','dinner');

select rtime,carb_code,carbs,dynamic_insulin
from insulin_carb_smoothed
where date(rtime)='2017-07-19';

