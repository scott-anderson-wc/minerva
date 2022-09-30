-- On Sep 28, 2022, Janice wrote about a plan to have test values of
-- cgm available in a table, that can then be copied, as needed to a
-- table for use by code they are testing.

-- the tables are source_cgm and latest_cgm.

-- Both tables will have columns similar to realtime_cgm, so I'm
-- copy/editing that code. The change is to add an auto_increment ID

-- We'll also have a testing_command table with one column that Janice
-- can use to initiate testing, with the other columns allowing the
-- cron job to communicate whether testing is in progress and when it
-- started.

use loop_logic;

-- this table will only ever have one row in it

drop table if exists testing_command;
create table testing_command(
     comm_id int primary key,
     command varchar(30) comment 'START, STOP for now, set to NULL by the cron job',
     status enum('OFF','ON'),
     start datetime comment 'null when not running, otherwise the time we started',
     msg text comment 'any error/info messages from the cron job'
);

-- default, testing is OFF
insert into testing_command values(1,'','OFF',NULL,'');

drop table if exists source_cgm;
create table source_cgm (
    user_id int not null default 7,
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
    used enum('NO','YES') comment 'allows us to reuse testing data. this marks it as used in the current run',
    primary key (user_id, rtime),
    index(rtime)
);

-- generate some data using the CGM data from 9/1/2022
insert into source_cgm
select user_id, rtime, dexcom_time, mgdl, trend, trend_code, 'NO'
from janice.realtime_cgm2
where date(rtime)='2022-09-01';

drop table if exists latest_cgm;
create table latest_cgm (
    cgmid int primary key auto_increment,
    user_id int not null default 7,
    time datetime,
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
    status enum('fake','real') comment 'the cron job that copies from source_cgm will specify that it is fake',
    index(time)
);
