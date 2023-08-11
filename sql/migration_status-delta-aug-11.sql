-- Remember to also update migration_status.sql!

-- adding two fields to keep track of migration status. It's annoying
-- to have the same chunk of code three times, but the alternative is
-- to have to remember to 'use' these three databases and avoid
-- accidentally putting them in the 'janice' database.

-- Actually, it's better to debug the syntax in loop_logic_scott and then
-- do the other two. That's why the first chunk is deleted.

use loop_logic_scott;


use loop_logic; 

alter table `migration_status` add column
      `last_run` timestamp NOT NULL default CURRENT_TIMESTAMP comment 'most recent run of migration cron job';
alter table `migration_status` add column
        `last_status` enum('error', 'no_data', 'starting', 'success') comment 'outcome associated with last_run';

use loop_logic_test;

alter table `migration_status` add column
      `last_run` timestamp NOT NULL default CURRENT_TIMESTAMP comment 'most recent run of migration cron job';
alter table `migration_status` add column
        `last_status` enum('error', 'no_data', 'starting', 'success') comment 'outcome associated with last_run';

