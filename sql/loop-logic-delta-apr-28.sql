-- More deltas for Loop logic

ALTER TABLE `run` add `run_state_entry_timestamp` datetime;
ALTER TABLE `run` add `new_state_entry_cgm_value` int;

-- this whole new table was added on 4/28
CREATE TABLE `run_state_history_table` (
  `run_state_history_id` int PRIMARY KEY AUTO_INCREMENT,
  `run_id` int,
  `user_id` int NOT NULL,
  `run_state_id` int,
  `run_state_entry_timestamp` timestamp,
  `new_state_entry_cgm_value` int
);
