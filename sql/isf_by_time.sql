-- To try to regress on time of day is hard, but I'm going to try.
-- the first step is to see if I can guess what the best shift is by
-- looking for the best place for the peak. I should probably use some
-- kind of local averaging to smooth it out a bit, but I can do that
-- later, maybe in Excel. For now, I'm just going to write out the
-- data with time of day, so I can graph it and get a sense.

select time,isf
from (select hour(rtime)*60+minute(rtime) as time, isf from isf_details) as t
order by time;

