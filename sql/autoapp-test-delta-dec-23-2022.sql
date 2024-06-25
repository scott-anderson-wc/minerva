use autoapp_test;

alter table loop_summary
add column 
  `linked_cgm_value` int comment 'the value that goes with the cgm_id. might be null'
after `linked_cgm_id`;

alter table run
add column
  `triggered_cgm_value` int NOT NULL
after `triggered_cgm_id`;

use loop_logic;

alter table loop_summary
add column 
  `linked_cgm_value` int comment 'the value that goes with the cgm_id. might be null'
after `linked_cgm_id`;

alter table run
add column
  `triggered_cgm_value` int NOT NULL
after `triggered_cgm_id`;

   



   



