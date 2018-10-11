# I am going to adopt the protocol that tables with names ending in a digit are processed versions
# and ones without are the original raw data

use janice;

# this table regularizes the timestamp as `date_time`, omitting the `date`
# and `epoch_time` fields.

CREATE TABLE `insulin_carb_2` (
  `user` varchar(20) NOT NULL,
  `date_time` datetime NOT NULL,
  `Basal_amt` varchar(16) NOT NULL,
  `temp_basal_down` varchar(5) NOT NULL,
  `temp_basal_up` varchar(5) NOT NULL,
  `temp_basal_duration` varchar(10) NOT NULL,
  `bolus_type` varchar(15) NOT NULL,
  `bolus_volume` varchar(7) NOT NULL,
  `Immediate_percent` varchar(8) NOT NULL,
  `extended_percent` varchar(9) NOT NULL,
  `duration` varchar(9) NOT NULL,
  `carbs` varchar(8) NOT NULL,
  `notes` text NOT NULL,
  `rec_num` int(9) NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`rec_num`),
  KEY `rec_num` (`rec_num`)
) ENGINE=InnoDB DEFAULT CHARSET=latin1;

# this also regularizes the date_time, omitting `time` and `epoch_time`

CREATE TABLE `cgm_2` (
  `user` varchar(20) NOT NULL,
  `date_time` datetime NOT NULL,
  `mgdl` varchar(4) NOT NULL,
  `rec_num` int(10) NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`rec_num`)
) ENGINE=InnoDB DEFAULT CHARSET=latin1;
