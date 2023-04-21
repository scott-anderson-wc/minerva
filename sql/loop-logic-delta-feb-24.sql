-- More deltas for Loop logic

-- omitted the 'use' statement, so we can source this in both loop_logic and autoapp_test

-- use loop_logic;

alter table loop_summary modify `bolus_value` double;
alter table loop_summary modify `carb_value` double;

-- Also, all the integer fields are storing just 0/1. So we should make them tinyint.

