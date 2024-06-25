use loop_logic;

Alter table loop_summary add column update_timestamp datetime after created_timestamp;
Alter table nocron_loop_summary add column update_timestamp datetime after created_timestamp;

use loop_logic_test;

Alter table loop_summary add column update_timestamp datetime after created_timestamp;
Alter table nocron_loop_summary add column update_timestamp datetime after created_timestamp;

