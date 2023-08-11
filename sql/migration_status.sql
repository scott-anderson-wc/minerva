-- See https://docs.google.com/document/d/1ZCtErlxRQmPUz_vbfLXdg7ap2hIz5g9Lubtog8ZqFys/edit#heading=h.umdjcuqs1gq4

use loop_logic_scott;

-- TODO: add FK constraint to an `accounts` table

drop table if exists migration_status;
CREATE TABLE `migration_status` (
  `user_id` int NOT NULL,
  `prev_autoapp_update` datetime NOT NULL,
  `prev_autoapp_migration` datetime NOT NULL,
  `prev_cgm_update` datetime NOT NULL,
  `prev_cgm_migration` datetime NOT NULL,
  `most_recent_command_id` int,
  `most_recent_command_timestamp` datetime,
  `last_run` datetime NOT NULL comment 'most recent run of migration cron job',
  `last_status` enum('error', 'no_data', 'starting', 'success') comment 'outcome associate with last_run'
  PRIMARY KEY (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

alter table `migration_status` add foreign key (`user_id`) references `user`(`user_id`);

-- Janice also wanted to keep a log, but still TBD. 
-- this omits a primary key, so we can log multiple things if they happen multiple times.
-- however, ideally, (user_id, prev_update) should be unique

-- These three datetimes should be in strictly increasing order

-- TODO: add FK constraint to an `accounts` table

drop table if exists migration_log;
create table `migration_log` (
  `user_id` int NOT NULL,
  `prev_update` datetime NOT NULL,
  `last_update` datetime NOT NULL,
  `last_migration` datetime NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8;
