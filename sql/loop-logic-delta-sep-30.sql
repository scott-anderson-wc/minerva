-- I edited the loop_logic.sql file to change the datatype of
-- loop_summary.pending to allow null. But I didn't want to discard
-- the migrated data, so I made this delta.

use loop_logic;

alter table loop_summary modify `pending` int comment 'can be null for non-command boluses';
