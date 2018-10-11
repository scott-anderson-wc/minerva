-- We first looked at duplicates of the cgm data (the implanted device
-- that provides readings every 5 minutes, but has to be regularly
-- uploaded to Diasend). Duplicates can appear for reasons that are
-- not clear.

-- This script is idempotent.

-- In this script, we look at duplicates in the mgm data (finger sticks)

-- Because of the arithmetic operations, even simple stuff like
-- computing differences between max and min, we need to have an mgm_1
-- table with proper datatypes.

drop table if exists mgm_1;
create table mgm_1 (
    user      varchar(20) not null, -- same as mgm
    date_time datetime not null,    -- different datatype
    rtime     datetime not null,    -- new field
    mgdl      mediumint unsigned,   -- different datatype
    rec_num   int(6)                -- same as mgm
);
insert into mgm_1
select user,cast(date as datetime),date5f(cast(date as datetime)),cast(mgdl as unsigned),rec_num
from mgm;

--  the output of the following is zero, which shows that there are no rows where
--  both the timestamp and the mgdl are repeated.

select 'num rtime and mgdl duplicates in mgm',
(select count(*) from (
	select rtime,min(mgdl) from mgm_1
	group by rtime
	having count(*) > 1 and min(mgdl) = max(mgdl)) as T) as num_row_duplicates;

-- It turns out that deleting duplicates using a subquery in the same table fails,
-- so, since we have to have an extra table anyhow, let's go ahead and pull out
-- all the duplicates:

drop table if exists mgm_duplicates;
create table mgm_duplicates like mgm_1;
insert into mgm_duplicates 
(select * from mgm_1 where rtime in 
    (select rtime
     from mgm_1
     group by rtime
     having count(*) > 1));

--  the output of this shows how many rows have duplicate timestamps (151) and where they occur

select 'num rtime duplicates in mgm';
select count(*) from
(select count(*) as len,min(rec_num)
 from mgm_1
 group by rtime
 having count(*) > 1) as t;

-- The output of this shows how many times an timestamp is repeated more than once.
-- Fortunately, it's pretty rare.

select 'num multiple rtime duplicates in mgm';
select count(*) from
(select rtime, count(*) as len,min(rec_num),max(rec_num)
 from mgm_duplicates
 group by rtime
 having count(*) > 2) as t;

--  the following shows the range that mgdl differs over a group

select 'mgdl range on rtime duplicates in mgm';
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
      from mgm_duplicates
      group by rtime
      having count(*) > 1) as T
order by len desc,diff desc,rtime asc;

-- Okay, time to implement the rule:  average if COV < 0.1 otherwise discard
-- We do this in several steps:
-- 1. create a new table mgm_noduplicates with date as primary key
-- 2. insert into mgm_noduplicates all rows that are in mgm_1 but not in mgm_duplicates
-- 3. insert into mgm_noduplicates all rows from mgm_duplicates with COV < 0.1
-- optionally, can drop mgm_1

-- first, record what we are doing

select 'discard',rtime,std(mgdl)/avg(mgdl) as cov
from mgm_duplicates
group by rtime
having std(mgdl)/avg(mgdl) > 0.1;

select 'average',rtime,avg(mgdl) as average
from mgm_duplicates
group by rtime
having std(mgdl)/avg(mgdl) <= 0.1;

-- now, step 1, create the table

drop table if exists mgm_noduplicates;
create table mgm_noduplicates (
       user       varchar(20) not null,  -- same as mgm
       rtime  datetime primary key,  -- different datatype and now primary key
       mgdl       mediumint unsigned     -- different datatype. Allow NULL
);

-- step 2, all non-duplicate rows

insert into mgm_noduplicates
(select user,rtime,mgdl
 from mgm_1
 where rtime not in (select rtime from mgm_duplicates));

-- step 3, all averages of groups with COV <= 0.1.
-- Note, we have to group by user because MySQL doesn't know we only have one value for that
-- When we have multiple users, we'll have to deal with duplicates for each user

insert into mgm_noduplicates
(select user,rtime,avg(mgdl)
 from mgm_duplicates
 group by user,rtime
 having std(mgdl)/avg(mgdl) <= 0.1);
