-- Scott's additions to the loop_logic database

-- use autoapp_test;                 -- in case we use this on its own

-- The following table added by Scott, to keep track of migration of data from autoapp.
-- we migrate data from autoapp when prev_autoapp_update < autoapp.dana_history_timestamp
-- we migrate data from 

drop table if exists migration_status;
CREATE TABLE `migration_status` (
  `user_id` int NOT NULL,
  `prev_autoapp_update` datetime NOT NULL,
  `prev_autoapp_migration` datetime NOT NULL,
  `prev_cgm_update` datetime NOT NULL,
  `prev_cgm_migration` datetime NOT NULL,
  PRIMARY KEY (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

-- Let's skip the log for now.

-- Janice also wanted to keep a log, but I'll keep it separately
-- this omits a primary key, so we can log multiple things if they happen multiple times.
-- however, ideally, (user_id, prev_update) should be unique

-- These three datetimes should be in strictly increasing order

-- TODO: add FK constraint to an `accounts` table

drop table if exists migration_log;
-- create table `migration_log` (
--   `user_id` int NOT NULL,
--   `prev_update` datetime NOT NULL,
--   `last_update` datetime NOT NULL,
--   `last_migration` datetime NOT NULL
-- ) ENGINE=InnoDB DEFAULT CHARSET=utf8;

-- migration_status is the latest; it's crucial. Initialized by hand
-- migration_log is write-only

alter table `migration_status` add foreign key (`user_id`) references `user`(`user_id`);
-- alter table `migration_log` add foreign key (`user_id`) references `user`(`user_id`);

replace into `migration_status` values(7,'2022-09-01','2022-09-01','2022-09-01','2022-09-01');

grant all privileges on autoapp_test.* to 'scott'@'localhost';
grant all privileges on autoapp_test.* to 'segun'@'%';

