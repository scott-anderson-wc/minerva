-- I edited the loop_logic.sql file to change the datatype of
-- loop_summary.bolus_value to allow null because not every command is
-- a bolus. But I didn't want to discard the migrated data, so I made
-- this delta.

use loop_logic;

alter table loop_summary modify `bolus_value` int comment 'will be null if command is not a bolus';

-- Also, all the integer fields are storing just 0/1. So we should make them tinyint
