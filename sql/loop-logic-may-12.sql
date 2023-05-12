drop database if exists loop_logic;
create database loop_logic;
use loop_logic;

CREATE TABLE `run_state_ref` (
  `run_state_id` int PRIMARY KEY AUTO_INCREMENT,
  `run_state` ENUM ('awaiting_first_run', 'regular_run', 'awaiting_new_cycle', 'all_runs_completed') NOT NULL
);

CREATE TABLE `run` (
  `run_id` int PRIMARY KEY AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `triggered_cgm_id` int NOT NULL,
  `glucose_range_id` int NOT NULL,
  `latest_notification_timestamp` datetime DEFAULT CURRENT_TIMESTAMP,
  `current_run_state_id` int DEFAULT 0,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `run_state_entry_timestamp` datetime, -- added on 4/28
  `new_state_entry_cgm_value` int       -- added on 4/28
);

-- this whole new table was added on 4/28
CREATE TABLE `run_state_history_table` (
  `run_state_history_id` int PRIMARY KEY AUTO_INCREMENT,
  `run_id` int,
  `user_id` int NOT NULL,
  `run_state_id` int,
  `run_state_entry_timestamp` timestamp,
  `new_state_entry_cgm_value` int
);


CREATE TABLE `glucose_range_type_ref` (
  `glucose_range_type_id` int PRIMARY KEY AUTO_INCREMENT,
  `glucose_range_type` ENUM ('low', 'in_range', 'high') NOT NULL
);

CREATE TABLE `glucose_range` (
  `glucose_range_id` int PRIMARY KEY AUTO_INCREMENT,
  `gluose_range_type_id` int NOT NULL,
  `lower_bound` int NOT NULL,
  `upper_bound` int NOT NULL
);

CREATE TABLE `mode` (
  `mode_id` int PRIMARY KEY AUTO_INCREMENT,
  `name` varchar(255),
  `user_id` int NOT NULL,
  `is_active` bool NOT NULL,
  `is_default` bool NOT NULL,
  `low_range_id` int NOT NULL,
  `in_range_id` int NOT NULL,
  `high_range_id` int NOT NULL,
  `cgm_target` int
);

CREATE TABLE `user` (
  `user_id` int PRIMARY KEY AUTO_INCREMENT,
  `full_name` varchar(255) NOT NULL,
  `email` varchar(255) UNIQUE NOT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE `realtime_cgm` (
    cgm_id int PRIMARY KEY AUTO_INCREMENT,
    user_id int not null,
    -- user varchar(20),
    -- rtime datetime,
    dexcom_time datetime,
    mgdl smallint,
    trend tinyint,
    trend_code enum('None',     -- 0
               'DoubleUp',      -- 1
               'SingleUp',      -- 2
               'FortyFiveUp',   -- 3
               'Flat',          -- 4
               'FortyFiveDown', -- 5
               'SingleDown',    -- 6
               'DoubleDown',    -- 7
               'NotComputable', -- 8
               'RateOutOfRange' -- 9
               )
    -- primary key (user, rtime),
    -- index (user_id, rtime),
    -- index(rtime)
);

drop index if exists realtime_cgm_index_0;
create index realtime_cgm_index_0
on realtime_cgm(dexcom_time);

-- should build an index on timestamps?

CREATE TABLE `loop_summary` (
  `loop_summary_id` int PRIMARY KEY AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `bolus_pump_id` int,
  `bolus_timestamp` datetime,
  `bolus_value` double,            -- was int. Fixed on 2/24/2023
  `carb_id` int,
  `carb_value` double, -- added on Feb 3, 2023. was int. Fixed on 2/24/2023
  `running_carb_interval` int,
  `command_id` int,
  `created_timestamp` datetime,
  `state` ENUM ('pending', 'abort', 'created', 'read', 'sent', 'done', 'error', 'timeout', 'canceled') NOT NULL,
  `type` ENUM ('profile', 'suspend', 'temporary_basal', 'bolus', 'dual_bolus', 'extended_bolus', 'cancel_temporary_basal') NOT NULL,
  `pending` int comment 'will be null for non-command bolus',
  -- the following two fields added on 12/1 at Janice's request, to be migrated from autoapp
  `completed` int, 
  `error` int, 
  `loop_command` int,
  `parent_decision` int,
  `linked_cgm_id` int comment 'will be null if no cgm found with matching timestamp',
  `temp_basal_timestamp` datetime,
  `temp_basal_percent` int,
  `running` int,
  `settled` int,
  `anchor` int, -- 0, 1 or 2. 1==anchor, 2==top-up
  `parent_involved` int,
  `running_bolus_interval` int,
  `running_topup_bolus_interval` int,
  `running_interval_max` int
);

CREATE TABLE `configuration` (
  `configuration_id` int PRIMARY KEY AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `isf_value_1` int NOT NULL,
  `isf_value_2` int NOT NULL,
  `isf_value_3` int NOT NULL,
  `isf_value_4` int NOT NULL,
  `isf_value_5` int NOT NULL,
  `isf_value_6` int NOT NULL,
  `isf_value_7` int NOT NULL,
  `isf_value_8` int NOT NULL,
  `isf_value_9` int NOT NULL,
  `isf_value_10` int NOT NULL,
  `isf_value_11` int NOT NULL,
  `isf_value_12` int NOT NULL,
  `significant_cgm_value` int NOT NULL,
  `command_timeout_mins` int NOT NULL,
  `no_pump_data_interval` int NOT NULL,
  `no_cgm_data_interval` int NOT NULL,
  `awaiting_new_cycle_interval` int NOT NULL,
  `time_delay_hybrid_control` int NOT NULL,
  `bolus_interval_mins` int, -- used for identifying anchor and top-up
  `topup_interval_mins` int,
  `max_bolus_interval_mins` int,
  `single_bolus_max` int,
  `running_bolus_max` int,
  `carb_interval_mins` int
);

CREATE TABLE `datetime_program` (
  `datetime_program_id` int PRIMARY KEY AUTO_INCREMENT,
  `datetime_program_guid` varchar(36) NOT NULL,
  `name` varchar(255) NOT NULL,
  `user_id` int NOT NULL,
  `mode_id` int NOT NULL,
  `is_default` bool NOT NULL,
  `is_active_monday` bool DEFAULT false,
  `is_active_tuesday` bool DEFAULT false,
  `is_active_wednesday` bool DEFAULT false,
  `is_active_thursday` bool DEFAULT false,
  `is_active_friday` bool DEFAULT false,
  `is_active_saturday` bool DEFAULT false,
  `is_active_sunday` bool DEFAULT false,
  `start_time` time NOT NULL,
  `end_time` time NOT NULL
);

CREATE UNIQUE INDEX `realtime_cgm_index_0` ON `realtime_cgm` (`user_id`, `dexcom_timestamp_utc`);

CREATE INDEX `realtime_cgm_index_1` ON `realtime_cgm` (`user_id`);

CREATE INDEX `datetime_program_index_2` ON `datetime_program` (`mode_id`);

CREATE INDEX `datetime_program_index_3` ON `datetime_program` (`user_id`);

ALTER TABLE `run` ADD FOREIGN KEY (`user_id`) REFERENCES `user` (`user_id`);

ALTER TABLE `run` ADD FOREIGN KEY (`triggered_cgm_id`) REFERENCES `realtime_cgm` (`cgm_id`);

ALTER TABLE `run` ADD FOREIGN KEY (`glucose_range_id`) REFERENCES `glucose_range` (`glucose_range_id`);

ALTER TABLE `run` ADD FOREIGN KEY (`current_run_state_id`) REFERENCES `run_state_ref` (`run_state_id`);

ALTER TABLE `glucose_range` ADD FOREIGN KEY (`gluose_range_type_id`) REFERENCES `glucose_range_type_ref` (`glucose_range_type_id`);

ALTER TABLE `mode` ADD FOREIGN KEY (`user_id`) REFERENCES `user` (`user_id`);

ALTER TABLE `mode` ADD FOREIGN KEY (`low_range_id`) REFERENCES `glucose_range` (`glucose_range_id`);

ALTER TABLE `mode` ADD FOREIGN KEY (`in_range_id`) REFERENCES `glucose_range` (`glucose_range_id`);

ALTER TABLE `mode` ADD FOREIGN KEY (`high_range_id`) REFERENCES `glucose_range` (`glucose_range_id`);

ALTER TABLE `realtime_cgm` ADD FOREIGN KEY (`user_id`) REFERENCES `user` (`user_id`);

ALTER TABLE `loop_summary` ADD FOREIGN KEY (`user_id`) REFERENCES `user` (`user_id`);

ALTER TABLE `loop_summary` ADD FOREIGN KEY (`linked_cgm_id`) REFERENCES `realtime_cgm` (`cgm_id`);

ALTER TABLE `configuration` ADD FOREIGN KEY (`user_id`) REFERENCES `user` (`user_id`);

ALTER TABLE `datetime_program` ADD FOREIGN KEY (`user_id`) REFERENCES `user` (`user_id`);

ALTER TABLE `datetime_program` ADD FOREIGN KEY (`mode_id`) REFERENCES `mode` (`mode_id`);

-- ================================================================

source loop-logic-configuration-variables.sql
source loop-logic-extras.sql
