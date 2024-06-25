-- Based on realtime_cgm.sql

set @target1 := '2022-02-01 07:10:02';
set @target2 := '2023-02-01 07:10:02';
set @target3 := '2023-01-01 22:50:00';

set @tg1 = date5f(@target1);
set @tg2 = date5f(@target2);
set @user_id := 7;

/* 
Lookups of "closest" CGM are important but time consuming. Trying to make that better.
*/

drop table if exists rt;
create table rt (
    user_id int not null,
    user varchar(20),
    rtime datetime,
    dexcom_time datetime,
    mgdl smallint,
    trend tinyint,
    trend_code enum('None',     -- 0
               'DoubleUp',      -- 1
               'SingleUp',      -- 2
               'FortyFiveUp',   -- 3
               'Flat',          -- 4
               'FortyFiveDown', -- 5
               'SingleDown',    -- 6
               'DoubleDown',    -- 7
               'NotComputable', -- 8
               'RateOutOfRange' -- 9
               ),
    primary key (user_id, rtime),
    index (user_id),
    index (rtime)
);

insert into rt
select * from realtime_cgm2;
