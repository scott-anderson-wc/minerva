-- for some reason, there wasn't a delta file for this addition, which
-- dates back to 12/23/2022. I created this file today because I
-- needed to add this field to loop_logic_test.

alter table `loop_summary` add `linked_cgm_value` int comment 'the value that goes with cgm_id. might be null' after `linked_cgm_id`;
