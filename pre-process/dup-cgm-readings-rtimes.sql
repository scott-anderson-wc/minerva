--  the output of the following is zero, which shows that there are no rows where
--  both the timestamp and the mgdl are repeated.

-- This script is idempotent.

select 'num rtime and mgdl duplicates',
(select count(*) from (
	select rtime,min(mgdl) from cgm_2
	group by rtime
	having count(*) > 1 and min(mgdl) = max(mgdl)) as T) as num_row_duplicates;

-- It turns out that deleting duplicates using a subquery in the same table fails,
-- so, since we have to have an extra table anyhow, let's go ahead and pull out
-- all the duplicates:

drop table if exists cgm_duplicates;
create table cgm_duplicates like cgm_2;
insert into cgm_duplicates 
(select * from cgm_2 where rtime in 
    (select rtime
     from cgm_2
     group by rtime
     having count(*) > 1));

--  the output of this shows how many rows have duplicate timestamps (971)

select 'num rtime duplicates';
select count(*) from
(select count(*) as len,min(rec_num)
 from cgm_duplicates
 group by rtime
 having count(*) > 1) as t;

--  the output of this shows how many times a timestamp is repeated more than once. It turns out to happen a lot.
--  quite often, a timestamp is repeated 12 or more times. (657 times)

select 'num multiple rtime duplicates';
select count(*) from
(select rtime, count(*) as len,min(rec_num),max(rec_num)
 from cgm_duplicates
 group by rtime
 having count(*) > 2) as t;

-- select 'multiple rtime duplicates';
-- select rtime, count(*) as len,min(rec_num),max(rec_num) from cgm_2 group by rtime having count(*) > 2;

--  the following shows the range that mgdl differs over a group

/*
select 'mgdl range on rtime duplicates';
select rtime as 'duplicated rtime',
       len,
       big,
       small,
       big-small as diff,
       lpad(format(100*big/small-100,2),6,' ') as '%more',
       lpad(format(mean,1),5,' ') as mean,
       lpad(format(std,1),5,' ') as stdev,
       lpad(format(std/mean,2),4,' ') as 'cov'
from (select rtime,
             count(*) as len,
	     max(mgdl) as big,
	     min(mgdl) as small,
	     avg(mgdl) as mean,
	     std(mgdl) as std
      from cgm_duplicates
      group by rtime
      having count(*) > 1) as T
order by len desc,diff desc,rtime asc;
*/

-- Okay, time to implement the rule:  average if COV < 0.1 otherwise discard
-- We do this in several steps:
-- 1. create a new table cgm_noduplicates with date as primary key
-- 2. insert into cgm_noduplicates all rows that are in cgm_2 but not in cgm_duplicates
-- 3. insert into cgm_noduplicates all rows from cgm_duplicates with COV < 0.1
-- optionally, can drop cgm_2

-- first, record what we are doing

select 'discard',rtime,rec_num from cgm_2 
where rtime in
(select rtime
 from cgm_duplicates
 group by rtime
 having std(mgdl)/avg(mgdl) > 0.1);

select 'average',rtime,avg(mgdl) as average from cgm_2 
where rtime in
(select rtime
 from cgm_duplicates
 group by rtime
 having std(mgdl)/avg(mgdl) <= 0.1)
group by rtime;

-- now, step 1, create the table

drop table if exists cgm_noduplicates;
create table cgm_noduplicates (
       user       varchar(20) not null,  -- same as cgm
       rtime  datetime primary key,  -- different datatype and now primary key
       mgdl       mediumint unsigned     -- different datatype. Allow NULL
);

-- step 2, all non-duplicate rows

insert into cgm_noduplicates
(select user,rtime,mgdl
 from cgm_2
 where rtime not in (select rtime from cgm_duplicates));

-- step 3, all averages of groups with COV <= 0.1.
-- Note, we have to group by user because MySQL doesn't know we only have one value for that
-- When we have multiple users, we'll have to deal with duplicates for each user

insert into cgm_noduplicates
(select user,rtime,avg(mgdl)
 from cgm_duplicates
 group by user,rtime
 having std(mgdl)/avg(mgdl) <= 0.1);
