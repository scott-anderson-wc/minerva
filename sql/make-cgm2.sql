/* differs from cgm_1 because date_time is a datetime and not a string, and we built an index on that, 
so that we can do joins efficiently. */


drop table if exists `cgm_2`;
CREATE TABLE `cgm_2` (
  `user` varchar(20) NOT NULL,
  `date_time` datetime NOT NULL,
  `mgdl` varchar(4) NOT NULL,
  `rec_num` int(10) NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`rec_num`),
  index (date_time)
) ENGINE=InnoDB DEFAULT CHARSET=latin1;

insert into cgm_2(user,date_time,mgdl,rec_num)
select user,str_to_date(time,'%m/%d/%Y %H:%i'),mgdl,rec_num from cgm_1;

/* I also have a python function to regularize the timestamps (5' intervals). */

