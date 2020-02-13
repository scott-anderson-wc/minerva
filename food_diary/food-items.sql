-- See if we can create a list of all the food items, separate from the quantity.

-- It *seems* that they are always written as "something something,
-- nn" where the nn is the number of carbs, I guess.
-- Let's see:

create temporary table food_items_and_carbs(
     item text
     );

insert into food_items_and_carbs select trim(lower(item1)) from food_diary_2 where item1 <> '';
insert into food_items_and_carbs select trim(lower(item2)) from food_diary_2 where item2 <> '';
insert into food_items_and_carbs select trim(lower(item3)) from food_diary_2 where item3 <> '';
insert into food_items_and_carbs select trim(lower(item4)) from food_diary_2 where item4 <> '';
insert into food_items_and_carbs select trim(lower(item5)) from food_diary_2 where item5 <> '';
insert into food_items_and_carbs select trim(lower(item6)) from food_diary_2 where item6 <> '';
insert into food_items_and_carbs select trim(lower(item7)) from food_diary_2 where item7 <> '';
insert into food_items_and_carbs select trim(lower(item8)) from food_diary_2 where item8 <> '';
insert into food_items_and_carbs select trim(lower(item9)) from food_diary_2 where item9 <> '';

select count(*) as 'total food items' from food_items_and_carbs;

select item from food_items_and_carbs limit 10;

-- 2200 matched the following regexp

select count(*) as 'total food items matching regexp' from food_items_and_carbs
where item REGEXP '.*,[[:space:]]*[[:digit:]]+';

-- here are some that didn't. They're pretty normal
select item as 'food items not matching regexp' from food_items_and_carbs
where item not REGEXP '.*,[[:space:]]*[[:digit:]]+'
limit 10;

update food_items_and_carbs
set item = substring_index(item,',',1);

select count(*) as 'total food items after update' from food_items_and_carbs;

-- here are all unique entries
select item as 'food items after update' from food_items_and_carbs group by item order by item;

select count(*) as 'total food items matching regexp now' from food_items_and_carbs
where item REGEXP '.*,[[:space:]]*[[:digit:]]+';


select count(*) as 'num school usual' from food_items_and_carbs
where item like '%school%';

-- eliminate duplicates yields just 805 items. Too many for a menu, but ...

select count(*) from
(select count(*) from food_items_and_carbs
group by item) as T;

-- 

-- select item,count(*) from food_items_and_carbs
-- group by item
-- having count(*) > 10;

