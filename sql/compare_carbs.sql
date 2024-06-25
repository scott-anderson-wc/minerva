use janice;

create temporary table carbs2023a (
    rtime datetime,
    carbs integer);

insert into carbs2023a
select janice.date5f(date), value
from autoapp.carbohydrate
where year(date) = '2023';

create temporary table carbs2023b (
    rtime datetime,
    carbs integer);

insert into carbs2023b
select rtime, carbs
from insulin_carb_smoothed_2
where year(rtime) = '2023' and carbs is not null;

select count(*) as '2023a count' from carbs2023a;
select count(*) as '2023b count' from carbs2023b;

select 'extra rtimes';
select * from carbs2023b where rtime not in (select rtime from carbs2023a);



