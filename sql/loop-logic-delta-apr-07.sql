-- More deltas for Loop logic

-- omitted the 'use' statement, so we can source this in both loop_logic and loop_logic_test

-- use loop_logic;

alter table loop_summary add `loop_processed` integer;

-- Also, all the integer fields are storing just 0/1. So we should make them tinyint.

