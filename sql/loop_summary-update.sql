-- Segun requested these two new columns on Nov 24, 2023

use loop_logic;

alter table loop_summary
add column loop_processed2 int default null
after loop_processed;

alter table loop_summary
add column notification datetime default null
after loop_processed2;

use loop_logic_test;

alter table loop_summary
add column loop_processed2 int default null
after loop_processed;

alter table loop_summary
add column notification datetime default null
after loop_processed2;
