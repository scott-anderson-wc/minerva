-- I edited the loop_logic-sep-22.sql file to add these two fields.
-- But I didn't want to discard the migrated data, so I made this
-- delta.

use loop_logic;

alter table loop_summary add `completed` int after `pending`;
alter table loop_summary add `error` int after `completed`;

-- Also, all the integer fields are storing just 0/1. So we should make them tinyint.

