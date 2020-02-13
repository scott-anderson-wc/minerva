create temporary table fd(
    user text,
    odate varchar(20), -- original date value
    rtime datetime,
    meal varchar(20),
    meal_id int,
    exercise varchar(7),
    meal_size varchar(6),
    primary key(meal_id)
    ,rec_num int(10)
    -- ,unique (datetime)
);

-- select user,date5f(str_to_date(date,'%c/%e/%Y %k:%i:%s')),meal
-- from food_diary
-- where date <> '' and date <> '-- ::00';


set @meal_id := 0;
insert into fd
select user,date,date5f(str_to_date(date,'%c/%e/%Y %k:%i:%s')),meal,(@meal_id := @meal_id + 1),null,null,rec_num
from food_diary
where date <> '' and date <> '-- ::00';

-- select rtime as 'non-unique mealtime',count(*) from fd
-- group by rtime
-- having count(*) > 1;

create temporary table dup_mealtimes (
    rtime datetime,
    count int
);    

insert into dup_mealtimes
select rtime,count(*) from fd
group by rtime
having count(*) > 1;

select rtime as 'worst duplicate mealtimes', count from dup_mealtimes order by count desc limit 10;

select sum(count) as 'total dup mealtimes' from dup_mealtimes;

-- select rec_num, odate, rtime from fd 
-- where rtime in ( select rtime from dup_mealtimes );

-- select * from food_diary
-- where date in (select odate from fd where rtime in (select rtime from dup_mealtimes where count = 9))\G

-- I give up for now
delete from fd where rtime in (select rtime from dup_mealtimes);

select count(*) as 'good unique mealtimes' from fd;

select year(rtime),month(rtime), count(*) from fd
group by year(rtime),month(rtime);

create temporary table fd_item(
    meal_id int,
    item text
    -- foreign key (meal_id) references fd(meal_id)
);

select count(*) as 'NUM RECORDS IN FD' from fd;

-- select meal, carb_code, carbs
-- from food_diary
