-- More deltas for Loop logic

-- omitted the 'use' statement, so we can source this in both loop_logic and autoapp_test

-- use loop_logic;

alter table loop_summary add `bolus_type` enum('correction','carb') after `bolus_timestamp`;

-- Also, all the integer fields are storing just 0/1. So we should make them tinyint.

