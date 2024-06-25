-- on April 15, 2023, I learned that there is a difference between the
-- loop_control table in autoapp_test versus autoapp. So I re-created
-- the table in autoapp_test using the following schema from a dump of
-- autoapp.

-- I also copied the data

use autoapp_test;

DROP TABLE IF EXISTS `loop_control`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `loop_control` (
  `user_id` int(11) NOT NULL,
  `mode` enum('off','direct','delayed','approved') NOT NULL,
  PRIMARY KEY (`user_id`),
  CONSTRAINT `automated_system_mode_fk` FOREIGN KEY (`user_id`) REFERENCES `accounts` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

insert into loop_control select * from autoapp.loop_control;
