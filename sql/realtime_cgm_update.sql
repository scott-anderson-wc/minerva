-- Sept 10, 2022
-- We added a user_id int value to the realtime_cgm2 table.

use janice;

-- testing first

-- drop table if exists realtime_cgm_test;
-- create table realtime_cgm_test  like realtime_cgm2;

-- insert into realtime_cgm_test
-- select * from realtime_cgm2;

-- alter table realtime_cgm_test add column `user_id` int not null first;
-- update realtime_cgm_test set `user_id` = 7;

-- ================ for real

alter table realtime_cgm2 add column `user_id` int not null first;
update realtime_cgm2 set `user_id` = 7;
