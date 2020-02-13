select min(real_date),max(real_date) from food_diary where real_date <> '';
select count(*) as 'count total entries' from food_diary;
select count(*) as 'non blank real_date' from food_diary where real_date <> '';

-- Note that the dates in food_diary are entered in a format w/o zero
-- padding, which is standard in Python, so such dates can't be
-- *generated* Such dates can be parsed, because the Python %m and %d
-- format specifiers are forgiving of the lack of zero padding, so
-- datetime.datetime.strptime('4/3/2016','%m/%d/%Y') works.

-- MySQL has operators %c and %e which allow non-zero padded months
-- and dates. That will allow us to switch to datetime representation.

select count(*) as 'count parseable dates' from food_diary
where str_to_date(real_date,"%c/%e/%Y") is not null;

select real_date as 'non-parseable date' from food_diary
where real_date <> '' and str_to_date(real_date,"%c/%e/%Y") is null;

select '2020 entries';
select real_date,meal from food_diary where real_date like '%2020';

select '2020 duplicates';
select real_date,meal,count(*) from food_diary where real_date like '%2020'
group by real_date,meal
having count(*) > 1;

-- this is a duplicate
select * from food_diary where real_date = '02/04/2020' and meal = 'dinner';

create temporary table fd(
    user text,
    odate varchar(20), -- original date value
    rtime datetime,
    meal varchar(20),
    meal_id int auto_increment,
    exercise varchar(7),
    meal_size varchar(6),
    primary key(meal_id)
    ,rec_num int(10)
    -- ,unique (datetime)
);

insert into fd(user,odate,meal,rec_num)
select user,real_date,meal,rec_num
from food_diary
where real_date <> '' and real_date <> '//' and real_date <> '20190917'
and str_to_date(real_date,"%c/%e/%Y") is not null;

select count(*) as 'count non-empty parseable real_date in FD' from fd;

-- select 'groups > 1 from fd';
-- select odate,meal,count(*) from fd
-- group by odate,meal
-- having count(*) > 1;

create temporary table dup_meals(
    date varchar(20),
    meal varchar(10),
    cnt int
    );

insert into dup_meals
select odate,meal,count(*) from fd
group by odate,meal
having count(*) > 1;

-- select * from fd, dup_meals where fd.odate=dup_meals.date and fd.meal = dup_meals.meal;

-- select 'rows from dup_meals';
-- select * from dup_meals;

select sum(cnt) as 'sum dup meals' from dup_meals;

select count(*) as 'dup meals'
from food_diary, dup_meals
where food_diary.real_date = dup_meals.date
  and food_diary.meal = dup_meals.meal;

-- list all the details
-- select food_diary.real_date,food_diary.meal,item1,item2,item3,item4,item5,item6,item7,item8,item9
-- from food_diary, dup_meals
-- where food_diary.real_date = dup_meals.date
--   and food_diary.meal = dup_meals.meal;

select count(*) as 'number of actual duplicates  (all items the same)'
from food_diary as A, food_diary as B, dup_meals as D
where A.real_date = D.date and A.meal = D.meal
  and B.real_date = D.date and B.meal = D.meal
  and A.rec_num <> B.rec_num
  and A.item1 = B.item1
  and A.item2 = B.item2
  and A.item3 = B.item3
  and A.item4 = B.item4
  and A.item5 = B.item5
  and A.item6 = B.item6
  and A.item7 = B.item7
  and A.item8 = B.item8
  and A.item9 = B.item9;

-- Okay, so there are 80 non-identical duplicates. We'll deal with
-- them some other time. For now, we'll delete them and see if we can
-- make do with the remaining 954 meals.

-- See the notes at the top of this file about datetime parsing.

drop table if exists food_diary_2;
create table food_diary_2(
       user	text,
       date	date,
       meal	varchar(10),
       item1	text,
       item2	text,
       item3	text,
       item4	text,
       item5	text,
       item6	text,
       item7	text,
       item8	text,
       item9	text,
       exercise	varchar(7),
       meal_size varchar(6),
       rec_num	int(10) primary key auto_increment
);
insert into food_diary_2
select user,str_to_date(real_date,"%c/%e/%Y"),meal,
item1,item2,item3,item4,item5,item6,item7,item8,item9,
exercise,meal_size,rec_num
from food_diary as FD
where real_date <> '' and real_date <> '//' and real_date <> '20190917'
and str_to_date(real_date,"%c/%e/%Y") is not null
and not exists
(select * from dup_meals as D
where FD.real_date = D.date and FD.meal = D.meal);

