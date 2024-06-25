use loop_logic;

-- try to get the last 30 rows, like tail

select loop_summary_id as id, bolus_pump_id as bid, bolus_timestamp, bolus_value as bolus, linked_cgm_id as cgm_id
from loop_summary
where loop_summary_id >= (-30 + (select max(loop_summary_id) from loop_summary));

