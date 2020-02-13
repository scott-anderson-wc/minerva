select count(*) as 'COUNT ALL ROWS' from food_diary;

select count(*) as 'NON-BLANK date_time' from food_diary where date_time <> '';

-- the previous showed that all the date_time columns are empty, so ignore them.

select count(*) as 'NON-BLANK date' from food_diary where date <> '';

select count(*) as 'COUNT NON-BLANK ROWS' from food_diary
where date<>'' and real_date <> '';

select count(*) as 'COUNT PARTIAL BLANK ROWS' from food_diary
where date <> '' and real_date = '' or
      date = '' and real_date <> '';

select count(*) as 'DISAGREE DATES' from food_diary
where date <> '' and real_date <> '' and date <> real_date;

-- select min(date),max(date) from food_diary;
-- select min(date),max(date) from food_diary where date <> '';

-- select min(real_date),max(real_date) from food_diary;
select min(real_date),max(real_date) from food_diary where real_date <> '';

-- select min(date_time),max(date_time) from food_diary;
-- select min(date_time),max(date_time) from food_diary where date_time <> '';

-- select date,str_to_date(date,'%c/%e/%Y %k:%i:%s') AS pdate
-- from food_diary where date <> '';

-- can the dates be parsed? Seems so!
select date as 'UNPARSEABLE NON-EMPTY DATES' from (
    select date,str_to_date(date,'%c/%e/%Y %k:%i:%s') AS pdate
    from food_diary where date <> '') as T
where T.pdate is null;

select count(*) as 'COUNT GOOD DATES' from (
    select date,str_to_date(date,'%c/%e/%Y %k:%i:%s') AS pdate
    from food_diary
    where date <> '' and date <> '-- ::00') as T
where T.pdate is not null;

-- select * from (
--     select real_date,str_to_date(real_date,'%c/%e/%Y %k:i%:%s') AS pdate
--     from food_diary where real_date <> '') as T
-- where T.pdate is not null;

-- ===============================================================

-- Are the rounded times unique?
select 'Non-unique rounded times';
select pdate,count(*)
from (
    select rec_num,date,date5f(str_to_date(date,'%c/%e/%Y %k:%i:%s')) as pdate
    from food_diary
    where date <> '' and date <> '-- ::00') as T
group by pdate
having count(*) > 1;

-- can we join with the ICS2 table?

select 'Records not matching times in ICS2';
select rec_num,date from food_diary
where date <> '' and date <> '-- ::00' and
    date5f(str_to_date(date,'%c/%e/%Y %k:%i:%s')) not in
        (select rtime from insulin_carb_smoothed_2);

-- ===============================================================

select distinct(meal) as 'MEAL KINDS' from food_diary;
select distinct(exercise) as 'EXERCISE KINDS' from food_diary;
select distinct(meal_size) as 'MEAL SIZES' from food_diary;

-- ================================================================

