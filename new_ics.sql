-- This table is not in use. It's referred to by code in db_generators.py, which
-- looks at using generators and batches of queries to allow us to process all the data
-- without crashing Python.

CREATE TABLE `insulin_carb_smoothed_3` (
  `row` int(11) auto_increment,
  `user` varchar(20) DEFAULT NULL,
  `rtime` datetime NOT NULL,
  `basal_amt` float DEFAULT NULL,
  `basal_gap` tinyint(4) DEFAULT '0',
  `basal_amt_12` float DEFAULT NULL,
  `total_bolus_volume` float DEFAULT NULL,
  `normal_insulin_bolus_volume` float DEFAULT NULL,
  `combination_insulin_bolus_volume` float DEFAULT NULL,
  `carbs` float DEFAULT NULL,
  `notes` text,
  `minutes_since_last_meal` mediumint(9) DEFAULT NULL,
  `minutes_since_last_bolus` mediumint(9) DEFAULT NULL,
  `carb_code` enum('before6','breakfast','lunch','dinner','snack','after9','rescue') DEFAULT NULL,
  `real_row` tinyint(4) DEFAULT '0',
  `rescue_carbs` tinyint(4) DEFAULT '0',
  `corrective_insulin` tinyint(4) DEFAULT '0',
  `ISF` float DEFAULT NULL,
  `Predicted_BG` float DEFAULT NULL,
  `ISF_trouble` varchar(50) DEFAULT NULL,
  `tags` varchar(50) DEFAULT NULL,
  `cgm` mediumint(8) unsigned DEFAULT NULL,
  `bg` mediumint(8) unsigned DEFAULT NULL,
  `cgm_slope_10` float DEFAULT NULL,
  `cgm_slope_30` float DEFAULT NULL,
  `cgm_slope_45` float DEFAULT NULL,
  `cgm_derivative_10` float DEFAULT NULL,
  `cgm_derivative_30` float DEFAULT NULL,
  `cgm_derivative_45` float DEFAULT NULL,
  `dynamic_carbs` float DEFAULT NULL,
  `dynamic_insulin` float DEFAULT '0',
  `rec_nums` varchar(50) DEFAULT NULL,
  `ISF_rounded` float DEFAULT NULL,
  PRIMARY KEY (`row`),
  index(`rtime`)
) ENGINE=InnoDB DEFAULT CHARSET=latin1;

insert into insulin_carb_smoothed_3
select row,user,rtime,basal_amt,basal_gap,basal_amt_12,total_bolus_volume,normal_insulin_bolus_volume,
       combination_insulin_bolus_volume,carbs,notes,minutes_since_last_meal,minutes_since_last_bolus,
       carb_code,real_row,rescue_carbs,corrective_insulin,ISF,Predicted_BG,ISF_trouble,tags,cgm,
       bg,cgm_slope_10,cgm_slope_30,cgm_slope_45,cgm_derivative_10,cgm_derivative_30,cgm_derivative_45,
       dynamic_carbs,dynamic_insulin,rec_nums,ISF_rounded
from insulin_carb_smoothed_2;
