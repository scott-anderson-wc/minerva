-- I copied loop_logic-sep-22.sql to loop_logic_feb_23.sql and added
-- this field.  But I didn't want to discard the migrated data, so I
-- made this delta.

-- omitted the 'use' statement, so we can source this in both loop_logic and autoapp_test

-- use loop_logic;

alter table loop_summary add `carb_value` int after `carb_id`;

-- Also, all the integer fields are storing just 0/1. So we should make them tinyint.

