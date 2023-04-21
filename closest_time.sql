use loop_logic;

set @target1 := '2022-02-01 07:10:02';
set @target2 := '2023-04-01 11:40:00';
set @uid := 7;

-- this finds the closest (in time) row to a given timestamp
-- (@target2) within a given window of time (here, I used 30 minutes)
-- working entirely in the database

-- this works, but I think that it's usually better to fetch the
-- window of rows around the target to Python and work there.
-- see the query in matching_bolus_within, which is the following:

select bolus_id, user_id, date, type, value, duration, server_date 
FROM autoapp.loop_summary
WHERE user_id = @uid
AND date between (@target2 - interval 30 minute) AND (@target2 + interval 30 minute);


-- mysql> describe realtime_cgm;
-- +----------------------+----------+------+-----+---------+----------------+
-- | Field                | Type     | Null | Key | Default | Extra          |
-- +----------------------+----------+------+-----+---------+----------------+
-- | cgm_id               | int(11)  | NO   | PRI | NULL    | auto_increment |
-- | user_id              | int(11)  | NO   | MUL | NULL    |                |
-- | trend                | int(11)  | NO   |     | NULL    |                |
-- | dexcom_timestamp_utc | datetime | NO   |     | NULL    |                |
-- | cgm_value            | int(11)  | NO   |     | NULL    |                |
-- +----------------------+----------+------+-----+---------+----------------+

-- select * from realtime_cgm
-- where abs(cgm_id - (select cgm_id from realtime_cgm where dexcom_timestamp_utc = @target2

show index from realtime_cgm;

select subtime(@target2, '00:30:00'), addtime(@target2, '00:30:00');

-- find rows in a 30-minute window around a target value.
-- this version is fast. It only examines 12 rows, which is good
-- the "use index" clause is NOT necessary.

select * from realtime_cgm use index (realtime_cgm_index_0)
where user_id = @uid
and subtime(@target2, '00:30:00') < dexcom_timestamp_utc
and dexcom_timestamp_utc < addtime(@target2, '00:30:00');

-- Use the previous query as a subquery, finding the min delta between
-- the target and the rows in that 60-minute window
-- this is also fast

select min(abs(unix_timestamp(dexcom_timestamp_utc) - unix_timestamp(@target2)))
from realtime_cgm use index (realtime_cgm_index_0)
where user_id = @uid
and subtime(@target2, '00:30:00') < dexcom_timestamp_utc
and dexcom_timestamp_utc < addtime(@target2, '00:30:00');

-- Find the actual closest row
-- this works and is fast



select * from realtime_cgm use index (realtime_cgm_index_0)
where user_id = @uid
and subtime(@target2, '00:30:00') < dexcom_timestamp_utc
and dexcom_timestamp_utc < addtime(@target2, '00:30:00')
and abs(unix_timestamp(dexcom_timestamp_utc) - unix_timestamp(@target2)) =
     (select min(abs(unix_timestamp(dexcom_timestamp_utc) - unix_timestamp(@target2)))
      from realtime_cgm use index (realtime_cgm_index_0)
      where user_id = @uid
      and subtime(@target2, '00:30:00') < dexcom_timestamp_utc
      and dexcom_timestamp_utc < addtime(@target2, '00:30:00'));
      





