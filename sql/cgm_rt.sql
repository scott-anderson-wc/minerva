# Created this table for Kevin Chung.

drop table if exists cgm_rt;
create table cgm_rt (
     user varchar(20),
     rtime datetime primary key, # timestamp rounded down to 5 minute
     mgdl mediumint,
     avg_1week float,
     avg_2week float,
     avg_4week float,
     avg_3month float);
