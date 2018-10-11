-- final checks:
select '================================================================';

select 'bad carb codes',count(*) from insulin_carb_smoothed_2
where carbs > 0 and carb_code not in   ('breakfast','lunch','snack','dinner','before6','after9','rescue');

select 'null dynamic carb values',count(*) from insulin_carb_smoothed_2
where dynamic_carbs is null;

select 'sum of carbs',sum(carbs),round(sum(dynamic_carbs)) from insulin_carb_smoothed_2;

select 'top 10 discrepant months';
select year,month,Asum,Bsum,Asum-Bsum   as diff from
    (select year(rtime) as year, month(rtime) as month, sum(carbs) as Asum, round(sum(dynamic_carbs)) as Bsum
     from insulin_carb_smoothed_2
     group by year(rtime),month(rtime)) as A
order by diff desc
limit 10;

select 'top 10 discrepant weeks of 2017'; select
week,Asum,Bsum,Asum-Bsum as diff from (select week(rtime) as week,
sum(carbs) as Asum, round(sum(dynamic_carbs)) as Bsum from
insulin_carb_smoothed_2 where year(rtime) = 2017 group by week(rtime))
as A order by diff desc limit 10;

