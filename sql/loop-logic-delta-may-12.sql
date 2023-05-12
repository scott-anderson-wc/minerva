-- Adding an index to loop_logic realtime_cgm. Probably eventually
-- obsolete, in favor of a computation of closest cgm that fetches a
-- window of times to python, but the index will still help for that.

-- also dropping the realtime_cgm_copy which we no longer need

create index realtime_cgm_index_0
on realtime_cgm(dexcom_time);

DROP TABLE IF EXISTS `realtime_cgm_copy`;
