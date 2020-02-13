--  this file regularizes the date fields and formats, so that
--  both insulin_carb_2 and cgm_2 have `date_time` as the standard field
--  with a datetime datatype.

--  This script works because bogus values have already been removed and the
--  remaining data is such that one field can act as the master. If that
--  were not the case, we would need to use something more flexible like
--  Python.

--  This takes only a few seconds.

-- this is a new version, using simpler datatypes like float instead of decimal(10,2)
-- this version also omits the unused fields
-- see .v1 if you want the older version

use janice;

-- named date5f() because this does a "floor" to the most recent 5 minute mark
-- should use this from now on, rather than date5()

drop function if exists date5f;
create function  date5f( d datetime )
returns  datetime  deterministic
return cast(concat(date(d), ' ', hour(d), ':', 5*floor(minute(d)/5))
	    as datetime);

-- testing it
-- select date5f( cast('2018-06-14 10:48:15' as datetime));
-- select date5f( cast('2018-06-14 10:59:59' as datetime));

drop table if exists insulin_carb_2;
CREATE TABLE `insulin_carb_2` (
 `user` varchar(20) NOT NULL,
 `date_time` datetime NOT NULL,
 `rtime` datetime not null,  -- rounded (floored) time
 `basal_amt` float, -- note lower case
 `basal_gap` tinyint default 0, /* 1 iff this row begins a gap */
 `bolus_type` varchar(15) NOT NULL,
 `bolus_volume` float,
 `duration` mediumint unsigned,
 `carbs` float,
 `notes` text NOT NULL,
 `rec_num` int(9) NOT NULL
AUTO_INCREMENT,
PRIMARY KEY (`rec_num`),
KEY `rec_num` (`rec_num`)
);

insert into insulin_carb_2(
       user,
       date_time,
       rtime,
       basal_amt,
       bolus_type,bolus_volume,
       duration,
       carbs,
       notes,
       rec_num)
select 
       user,
       str_to_date(date_time,'%Y%m%d%H%i'),
       date5f(str_to_date(date_time,'%Y%m%d%H%i')),
       if(Basal_amt='',NULL,Basal_amt),
       bolus_type,
       if(bolus_volume='',NULL,bolus_volume),
       if(duration='',NULL,duration),
       if(carbs='',NULL,carbs),
       notes,
       rec_num
 from insulin_carb_1;

--  can now drop insulin_carb_1;

drop table if exists cgm_2;
create table cgm_2 (
    user varchar(20), -- same as cgm_1
    date_time datetime,
    rtime datetime,
    mgdl mediumint unsigned,
    rec_num int(10)
);
    
insert into cgm_2(user,date_time,rtime,mgdl,rec_num)
select user, date_time, date5f(date_time), cast(mgdl as unsigned), rec_num
from cgm_1;
