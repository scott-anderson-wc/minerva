-- See https://docs.google.com/document/d/1ZCtErlxRQmPUz_vbfLXdg7ap2hIz5g9Lubtog8ZqFys/edit#heading=h.umdjcuqs1gq4

use janice;

-- TODO: add FK constraint to an `accounts` table

drop table if exists migration_status;
CREATE TABLE `migration_status` (
  `user_id` int NOT NULL,
  `prev_update` datetime NOT NULL,
  `migration_time` datetime NOT NULL,
  PRIMARY KEY (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

-- Janice also wanted to keep a log, but I'll keep it separately
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
