-- the original realtime_cgm table is okay, but it has 3 date fields,
-- none of which is a date type; they are all varchar. So is mgdl,
-- which really should be tinyint.

drop table if exists realtime_cgm2;
create table realtime_cgm2 (
    user varchar(20),
    rtime datetime,
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
    rec_num int(10) not null auto_increment,
    primary key (rec_num),
    index(rtime)
);

insert into realtime_cgm2
select user, date5f(date), mgdl,
case
    when trend = '' then 0
    when trend > 9 then 0
    else trend
end,
case
    when trend = '' then 0
    when trend > 9 then 0
    else trend
end,
rec_num
from realtime_cgm
where mgdl <> '';

