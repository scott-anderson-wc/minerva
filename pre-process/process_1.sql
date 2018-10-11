--  I am going to adopt the protocol that tables with names ending in a digit are processed versions
--  and ones without are the original raw data

use janice;

--  The first ones just delete bogus rows.

--  Another problem is datatypes. If I compute min(mgdl) and max(mgdl) on the following two rows:

--  select * from cgm_1 where rec_num in (436462, 193712);
--  +------+---------------------+--------------+------------+------+---------+
--  | user | date                | date_time    | epoch_time | mgdl | rec_num |
--  +------+---------------------+--------------+------------+------+---------+
--  | Hugh | 2014-08-27 18:19:00 | 201408271819 | 1409163540 | 105  |  193712 |
--  | Hugh | 2014-08-27 18:19:00 | 201408271819 | 1409163540 | 97   |  436462 |
--  +------+---------------------+--------------+------------+------+---------+
--  2 rows in set (0.01 sec)

--  find that the max is 97 and the min is 105, because both are text values.

--  Note that I will use unsigned medium ints for mgdl values. The
--  largest mgdl value I have seen is 435, which does not fit in a
--  tinyint of either sort.

-- I'm also going to drop the extra date fields and standardize on
-- date_time since that seems most descriptive.

drop table if exists `insulin_carb_1`;

create table insulin_carb_1 like insulin_carb;  -- FIX THIS

-- CREATE TABLE `insulin_carb_1` (
--      user varchar(20) not null, -- same as insulin_carb
--     date_time datetime not null, -- new datatype
--      Basa

insert into insulin_carb_1 (select * from `insulin_carb`);

delete from insulin_carb_1 where
date_time = '' and
Basal_amt = '' and
temp_basal_down = '' and
temp_basal_up = '' and
temp_basal_duration = '' and
bolus_type = '' and
bolus_volume = '' and
Immediate_percent = '' and
extended_percent = '' and
duration = '' and
carbs = '' and
notes = '';

--  Next, I learned that there are some early rows where date and date_time
--  are both the empty string and epoch is zero. There are only 10 such, and all
--  before May 18, 2014. Witness:

select 'rows missing date info', count(*) from insulin_carb_1
where date = '' and date_time = '' and epoch_time = '0';

select 'max rec_num with missing date info', max(rec_num) from insulin_carb_1
where date = '' and date_time = '' and epoch_time = '0';

--  So, I am deleting those bogus data:

delete from insulin_carb_1 
where date = '' and date_time = '' and epoch_time = '0';

drop table if exists `cgm_1`;
create table `cgm_1` (
       user       varchar(20) not null,  -- same as cgm
       date_time  datetime,     -- different datatype
       mgdl       mediumint unsigned, -- different datatype. Allow NULL
       rec_num    int(10) primary key  -- same as cgm
);

insert into cgm_1
(select user,cast(date as datetime),cast(mgdl as unsigned), rec_num
from cgm
where user <> '' and date <> '' and date_time <> '' and epoch_time <> '' and mgdl <> '');

