alter table migration_status add column `most_recent_command_id` int;
alter table migration_status add column `most_recent_command_timestamp` datetime;

