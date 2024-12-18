/* In December 2022, we decided to put the loop_logic tables into the
same database with the autoapp tables. That will allow Segun to do all
his stuff in a single database.

For now, those tables are going in autoapp_test, which is separate
from the live autoapp database that Mattias's app reads and writes.

There haven't been any changes to the autoapp tables in a few months,
so this batch file assumes those will say unchanged, so this file does
*not* drop the database or any tables. When/if we revise this
database, we should do it incrementally with ALTER statements and edit
this file to match. This file is meant to be used only once.

This file was based on the dbdiagram export on Sept 11, 2022 and
modified since then. If there are any changes to dbdiagram then, they
need to be propagated to here.

TODO:

I think some of the datatypes, particular 0/1 values, should be
reduced from int to tinyint. I'm not sure they should go all the way
to bit(1), as Mattias has done, because those are hard to read in the
MySQL shell, but that's a minor concern, so maybe bit(1) is best. But
int is clearly excessive. Enum (no,yes) might be best of all. Or
the bool datatype! 

I also sourced this in autoapp so that they have the same tables

Scott Anderson
12/16/2022
*/

-- use autoapp_test;  // use source instead

CREATE TABLE `run_state_ref` (
  `run_state_id` int PRIMARY KEY AUTO_INCREMENT,
  `run_state` ENUM ('awaiting_first_run', 'regular_run', 'awaiting_new_cycle', 'all_runs_completed') NOT NULL
);

CREATE TABLE `run` (
  `run_id` int PRIMARY KEY AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `triggered_cgm_id` int NOT NULL,
  `triggered_cgm_value` int NOT NULL, -- added on 12/23/2022
  `glucose_range_id` int NOT NULL,
  `latest_notification_timestamp` datetime DEFAULT CURRENT_TIMESTAMP,
  `current_run_state_id` int DEFAULT 0,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE `glucose_range_type_ref` (
  `glucose_range_type_id` int PRIMARY KEY AUTO_INCREMENT,
  `glucose_range_type` ENUM ('low', 'in_range', 'high') NOT NULL
);

CREATE TABLE `glucose_range` (
  `glucose_range_id` int PRIMARY KEY AUTO_INCREMENT,
  `glucose_range_type_id` int NOT NULL,
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
  `cgm_id` int PRIMARY KEY AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `trend` int NOT NULL,
  `dexcom_timestamp_utc` datetime NOT NULL,
  `cgm_value` int NOT NULL
);

CREATE TABLE `loop_summary` (
  `loop_summary_id` int PRIMARY KEY AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `bolus_pump_id` int,
  `bolus_timestamp` datetime,
  `bolus_value` int,
  `carb_id` int,
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
  `linked_cgm_value` int comment 'the value that goes with the cgm_id. might be null', -- added 12/23/2022
  `temp_basal_timestamp` datetime,
  `temp_basal_percent` int,
  `running` int,
  `settled` int,
  `anchor` int,
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
  `bolus_interval_mins` int,
  `topup_interval_mins` int,
  `max_bolus_interval_mins` int,
  `single_bolus_max` int,
  `running_bolus_max` int
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

ALTER TABLE `glucose_range` ADD FOREIGN KEY (`glucose_range_type_id`) REFERENCES `glucose_range_type_ref` (`glucose_range_type_id`);

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
