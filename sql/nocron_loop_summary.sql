-- MySQL dump 10.13  Distrib 5.7.42, for Linux (x86_64)
--
-- Host: localhost    Database: loop_logic
-- ------------------------------------------------------
-- Server version	5.7.42-0ubuntu0.18.04.1

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `nocron_loop_summary`
--

DROP TABLE IF EXISTS `nocron_loop_summary`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `nocron_loop_summary` (
  `loop_summary_id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` int(11) NOT NULL,
  `bolus_pump_id` int(11) DEFAULT NULL,
  `bolus_timestamp` datetime DEFAULT NULL,
  `bolus_type` enum('correction','carb') DEFAULT NULL,
  `bolus_value` double DEFAULT NULL,
  `carb_id` int(11) DEFAULT NULL,
  `carb_timestamp` datetime DEFAULT NULL,
  `carb_value` double DEFAULT NULL,
  `running_carb_interval` int(11) DEFAULT NULL,
  `command_id` int(11) DEFAULT NULL,
  `created_timestamp` datetime DEFAULT NULL,
  `state` enum('pending','abort','created','read','sent','done','error','timeout','canceled') DEFAULT NULL,
  `type` enum('profile','suspend','temporary_basal','bolus','dual_bolus','extended_bolus','cancel_temporary_basal') DEFAULT NULL,
  `pending` int(11) DEFAULT NULL COMMENT 'can be null for non-command boluses',
  `completed` int(11) DEFAULT NULL,
  `error` int(11) DEFAULT NULL,
  `loop_command` int(11) DEFAULT NULL,
  `parent_decision` int(11) DEFAULT NULL,
  `linked_cgm_id` int(11) DEFAULT NULL COMMENT 'will be null if no cgm found with matching timestamp',
  `linked_cgm_value` int(11) DEFAULT NULL COMMENT 'the value that goes with the cgm_id. might be null',
  `temp_basal_timestamp` datetime DEFAULT NULL,
  `temp_basal_percent` int(11) DEFAULT NULL,
  `running` int(11) DEFAULT NULL,
  `settled` int(11) DEFAULT NULL,
  `anchor` int(11) DEFAULT NULL,
  `parent_involved` int(11) DEFAULT NULL,
  `running_bolus_interval` int(11) DEFAULT NULL,
  `running_topup_bolus_interval` int(11) DEFAULT NULL,
  `running_interval_max` int(11) DEFAULT NULL,
  `loop_processed` int(11) DEFAULT NULL,
  `loop_processed2` int(11) DEFAULT NULL,
  `notification` datetime DEFAULT NULL,
  PRIMARY KEY (`loop_summary_id`),
  KEY `user_id` (`user_id`),
  KEY `linked_cgm_id` (`linked_cgm_id`)
) ENGINE=InnoDB DEFAULT CHARSET=latin1;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `nocron_loop_summary`
--

LOCK TABLES `nocron_loop_summary` WRITE;
/*!40000 ALTER TABLE `nocron_loop_summary` DISABLE KEYS */;
/*!40000 ALTER TABLE `nocron_loop_summary` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2023-11-24 12:07:21
