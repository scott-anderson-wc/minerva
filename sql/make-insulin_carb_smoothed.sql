/* This is the table we actually use for display and calculations.

insulin_carb  is the original raw data, 
insulin_carb_1  has the bogus rows removed,
insulin_carb_2  has date_time as a datetime, rather than varchar

insulin_carb_grouped has only one row per timestamp, rounded to 5'

The original insulin_carb table had a bolus_volume and bolus_type
field which makes sense except for times when there are two types
given at the same time. That is, the _grouped table has to deal with
busy events like:

select bolus_type,bolus_volume,duration,carbs,notes,rec_num 
from insulin_carb_2 where date_time = '2018-06-06 19:19:00';

+-------------+--------------+----------+-------+---------------------+---------+
| bolus_type  | bolus_volume | duration | carbs | notes               | rec_num |
+-------------+--------------+----------+-------+---------------------+---------+
| Combination |            4 |       60 |  NULL | Combination unknown |  120345 |
|             |         NULL |     NULL |    57 |                     |  120346 |
| Normal      |       0.4095 |     NULL |  NULL |                     |  120347 |
+-------------+--------------+----------+-------+---------------------+---------+
3 rows in set (0.03 sec)

I resolved this by having separate columns for Normal Insulin and
Combination Insulin:

normal_insulin_bolus_volume
combination_insulin_bolus_volume

I *also* have a bolus_volume that is the sum of the two.

Where the bolus_type is blank, that's a carbs entry.

================================================================

insulin_carb_smoothed fills in with virtual rows, so we have exactly
one timestamp per 5'. It also adds the bg and cgm values from the mgm
and cgm tables.

I added these columns:

tags:  like rescue_carbs
real_row: 0/1      true if it was from the raw data
rescue_carbs: 0/1
rescue_insulin: 0/1
minutes_since_last_meal
minutes_since_last_bolus
carb_code: before6/breakfast/lunch/dinner/snack/after9/rescue
cgm: value from the cgm_2 table
bg: finger stick value from the mgm table, if any
cgm_slope_10:  delta of cgm value from the value from 10 minutes earlier
cgm_slope_30:  similar
cgm_slope_45:  similar
cgm_derivative_10: delta of this cgm_slope_10 value from the one 10 minutes earlier
cgm_derivative_30: similar
cgm_derivative_45: similar
dynamic_insulin:  average of insulin input weighted by Insulin Action Curve (IAC) based on Lispro curve
carbs_on_board:   average of carb input weighted by Carb Action Curve (CAC) that depends on prior meal

*/

drop table if exists `insulin_carb_grouped`;
CREATE TABLE `insulin_carb_grouped` ( 
    `user` varchar(20) DEFAULT NULL,
    `rtime` datetime primary key NOT NULL,   -- for rounded time, though it's really floored
    `basal_amt` float DEFAULT NULL,
    `basal_gap` tinyint default 0, /* 1 iff this row begins a gap */
    `basal_amt_12` float DEFAULT NULL,
    `total_bolus_volume` float default null,
    `normal_insulin_bolus_volume` float DEFAULT NULL,
    `combination_insulin_bolus_volume` float DEFAULT NULL,
    `carbs` float DEFAULT NULL,
    `notes` text DEFAULT NULL,
    `minutes_since_last_meal` mediumint default null,
    `minutes_since_last_bolus` mediumint default null,
    `carb_code` enum('before6','breakfast','lunch','dinner','snack','after9','rescue'),
    `real_row` tinyint default 0,
    `rescue_carbs` tinyint default 0,
    `corrective_insulin` tinyint default 0,
    `tags` varchar(50),
    `cgm` mediumint unsigned,   /* from the cgm_2 table */
    `bg`  mediumint unsigned,   /* from the mgm table */
    `cgm_slope_10` float,
    `cgm_slope_30` float,
    `cgm_slope_45` float,
    `cgm_derivative_10` float,
    `cgm_derivative_30` float,
    `cgm_derivative_45` float,
    `dynamic_carbs` float,  -- AKA carbs_on_board
    `dynamic_insulin` float default 0,
    `rec_nums` varchar(50) /* group_concat from the insulin_carb_2 table */
) ENGINE=InnoDB DEFAULT CHARSET=latin1;


-- first, all the user, rtime values
insert into insulin_carb_grouped(user,rtime,real_row)
select user,rtime,1 from
insulin_carb_2 group by user,rtime;

select count(*) as 'all rtime values in insulin_carb_2'
from (select rtime from insulin_carb_2 group by rtime) as T;

select count(*) as 'all rtime values in ics'
from ics;

-- from now on, we only update

-- First, basal_amt, where we take the basal_amt value from the last
-- row (largest rec_num) in the group

update insulin_carb_grouped as icg,
(select rtime,basal_amt from insulin_carb_2
             inner join (select rtime,max(rec_num) as max_rec_num from insulin_carb_2 group by rtime) as G
	     using (rtime)
	     where insulin_carb_2.rec_num = G.max_rec_num) as T
set icg.basal_amt = T.basal_amt
where icg.rtime = T.rtime;

update insulin_carb_grouped as icg,
(select rtime,max(basal_gap) as mbg from insulin_carb_2 group by rtime) as G
set icg.basal_gap = G.mbg
where icg.rtime = G.rtime;


-- here are some troublesome entries in the original data, where there
-- is more than one basal_amt on a given timestamp. This gets even
-- worse when the data is grouped by rounded timestamp.

select date_time, basal_amt, rec_num from insulin_carb_2
where date_time in (select date_time from insulin_carb_2
                    group by date_time
		    having count(*) > 1
		    and min(basal_amt) < max(basal_amt));

-- here is how we dealt with them in the icg data

select rtime, basal_amt from insulin_carb_grouped
where rtime in (select min(rtime) from insulin_carb_2
                group by date_time
		having count(*) > 1
		and min(basal_amt) < max(basal_amt));

-- next, insulin. We distinguish different bolus_types and sum the
-- bolus_volumes

update insulin_carb_grouped as icg, (select rtime,sum(bolus_volume) as tbv
             from insulin_carb_2
	     group by rtime) as T
set icg.total_bolus_volume = T.tbv
where icg.rtime = T.rtime;

update insulin_carb_grouped as icg, (select rtime,sum(bolus_volume) as nibv
             from insulin_carb_2
	     where bolus_type = 'Normal'
	     group by rtime) as T
set icg.normal_insulin_bolus_volume = T.nibv
where icg.rtime = T.rtime;

update insulin_carb_grouped as icg, (select rtime,sum(bolus_volume) as cibv
             from insulin_carb_2
	     where bolus_type = 'Combination'
	     group by rtime) as T
set icg.combination_insulin_bolus_volume = T.cibv
where icg.rtime = T.rtime;

-- check the bolus_volume sums
select format(sum(bolus_volume),2) as 'total sum from IC2' from insulin_carb_2;
select format(sum(total_bolus_volume),2) as 'total sum from ICG' from insulin_carb_grouped;
select format(sum(bolus_volume),2) as 'Normal sum from IC2' from insulin_carb_2 where bolus_type = 'Normal';
select format(sum(normal_insulin_bolus_volume),2) as 'Normal sum from ICG' from insulin_carb_grouped;
select format(sum(bolus_volume),2) as 'Combo  sum from IC2' from insulin_carb_2 where bolus_type = 'Combination';
select format(sum(combination_insulin_bolus_volume),2) as 'Combo sum from ICG' from insulin_carb_grouped;

-- next, carbs. sum these over the groups

update insulin_carb_grouped as icg,
(select rtime,sum(carbs) as carbs from insulin_carb_2 group by rtime) as T
set icg.carbs = T.carbs
where icg.rtime = T.rtime;

-- check the carbs
select sum(carbs) as 'carb sum from insulin_carb_2' from insulin_carb_2;
select sum(carbs) as 'carb sum from ics' from insulin_carb_grouped;

-- next, notes and rec_nums. concatenate these.

update insulin_carb_grouped as icg,
(select rtime,group_concat(notes SEPARATOR '&') as notes,group_concat(rec_num SEPARATOR '&') as rec_nums
from insulin_carb_2 group by rtime) as T
set icg.notes = T.notes, icg.rec_nums = T.rec_nums
where icg.rtime = T.rtime;

drop table if exists insulin_carb_smoothed;
create table insulin_carb_smoothed like insulin_carb_grouped;

drop table if exists insulin_carb_smoothed_2;
create table insulin_carb_smoothed_2 like insulin_carb_grouped;

-- Added these two columns to compute ISF
alter table insulin_carb_smoothed_2 add column ISF float after corrective_insulin;
alter table remove column ISF_trouble;
alter table insulin_carb_smoothed_2 add column ISF_trouble varchar(50) after ISF;


select 'all done with make-insulin_carb_smoothed.sql';
