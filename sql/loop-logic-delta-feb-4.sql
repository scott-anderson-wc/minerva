-- Janice asked for this field to be renamed in an email on Feb 2, 2024
-- remember to copy the file that the symlink loop-logic.sql points to and fix the symlink
-- Then remember to dump the structure of nocron:
-- mysqldump --no-data loop_logic nocron_loop_summary > nocron_loop_summary-DATE.sql

use loop_logic;

-- the syntax in MySQL 5.7 is different from MySQL 8.0

Alter table loop_summary change column running_carb_interval running_carb_bolus_interval int;
Alter table nocron_loop_summary change column running_carb_interval running_carb_bolus_interval int;

use loop_logic_test;

Alter table loop_summary change column running_carb_interval running_carb_bolus_interval int;
Alter table nocron_loop_summary change column running_carb_interval running_carb_bolus_interval int;

