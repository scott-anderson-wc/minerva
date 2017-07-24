# this file regularizes the date fields and formats, so that
# both insulin_carb_2 and cgm_2 have `date_time` as the standard field
# with a datetime datatype.

# This script works because bogus values have already been removed and the
# remaining data is such that one field can act as the master. If that
# were not the case, we would need to use something more flexible like
# Python.

# This takes only a few seconds.

use janice;

# the following makes it idempotent

drop table if exists insulin_carb_2;
CREATE TABLE `insulin_carb_2` (
 `user` varchar(20) NOT NULL,
 `date_time` datetime NOT NULL,
 `basal_amt` decimal(10,3), 	-- note, lower case
 `temp_basal_down` varchar(5),
 `temp_basal_up` varchar(5),
 `temp_basal_duration` varchar(10),
 `bolus_type` varchar(15) NOT NULL,
 `bolus_volume` decimal(10,2),
 `Immediate_percent` varchar(8),
 `extended_percent` varchar(9),
 `duration` varchar(9),
 `carbs` decimal(10,2),
 `notes` text NOT NULL,
 `rec_num` int(9) NOT NULL
AUTO_INCREMENT,
PRIMARY KEY (`rec_num`),
KEY `rec_num` (`rec_num`)
);

insert into insulin_carb_2(
       user,date_time,
       basal_amt,
       temp_basal_down,temp_basal_up,temp_basal_duration,
       bolus_type,bolus_volume,
       Immediate_percent, extended_percent,
       duration,
       carbs,
       notes,
       rec_num)
select 
       user,str_to_date(date_time,'%Y%m%d%H%i'),
       if(Basal_amt='',NULL,cast(Basal_amt as decimal(10,3))),
       temp_basal_down,temp_basal_up,temp_basal_duration,
       bolus_type,
       if(bolus_volume='',NULL,cast(bolus_volume as decimal(10,2))),
       Immediate_percent, extended_percent,
       duration,
       if(carbs='',NULL,cast(carbs as decimal(10,2))),
       notes,
       rec_num
 from insulin_carb_1;

# can now drop insulin_carb_1;

delete from cgm_2;
insert into cgm_2(user,date_time,mgdl,rec_num)
select user, str_to_date(time,'%m/%d/%Y %H:%i'), mgdl, rec_num
from cgm_1;

