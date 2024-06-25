-- More deltas for Loop logic

use loop_logic;

-- ALTER TABLE `configuration` add `waitTimeAfterParentCancelsLoopBolus` int;

-- Segun created this in loop_logic_test; Copying it to loop_logic

CREATE TABLE `loop_bolus_commands` (
  `loop_command_id` int(11) NOT NULL AUTO_INCREMENT,
  `command_id` int(11) NOT NULL,
  `user_id` int(11) NOT NULL,
  `bolus_amount` double NOT NULL,
  `created_timestamp` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_timestamp` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `linked_cgm_id` int(11) DEFAULT NULL,
  `linked_cgm_value` int(11) DEFAULT NULL,
  PRIMARY KEY (`loop_command_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

-- insert into loop_bolus_commands select * from loop_logic_test.loop_bolus_commands;
