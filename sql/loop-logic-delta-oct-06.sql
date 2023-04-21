-- I edited the loop_logic.sql file to change the datatype of
-- loop_summary.linked_cgm to allow null. But I didn't want to discard
-- the migrated data, so I made this delta.

use loop_logic;

alter table loop_summary modify `linked_cgm_id` int comment 'will be null if no cgm found with matching timestamp';
