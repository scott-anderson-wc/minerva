-- the original realtime_cgm table is okay, but it has 3 date fields,
-- none of which is a date type; they are all varchar. So is mgdl,
-- which really should be tinyint.

-- This was completely revised in August 2022 because of the re-written Dexcom CGM download. 
-- We added the dexcom timestamp so that we could detect the NoData situation and to fill in
-- past data. If there is NoData, mgdl, trend and trend_code will all be NULL

-- BTW, trend_code is entirely redundant with trend. Indeed, trend == trend_code+0
-- However, if they come up with a new code, we'll be able to store it in trend even
-- if we can't store it in trend_code.

-- I got rid of the rec_num field, since we almost never use it and it makes more sense
-- to use (user,rtime) as the key. That also allows the ON-DUPLICATE-KEY trick. 

use janice;

drop table if exists realtime_cgm2;
create table realtime_cgm2 (
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
    primary key (user, rtime),
    index(rtime)
);

insert into realtime_cgm2
select user, date5f(date), NULL, min(mgdl), 
min(case
    when trend = '' then 0
    when trend > 9 then 0
    else trend
end),
min(case
    when trend = '' then 0
    when trend > 9 then 0
    else trend
end)
from realtime_cgm
where mgdl <> ''
group by user, date5f(date);
