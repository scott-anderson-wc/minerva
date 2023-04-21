-- More deltas for Loop logic

alter table loop_summary add `carb_timestamp` datetime after `carb_id`;

-- Also, all the integer fields are storing just 0/1. So we should make them tinyint.

