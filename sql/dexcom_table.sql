use janice;

drop table if exists dexcom_cgm;
create table dexcom_cgm (
   cgmId int,
   userId int,
   trend int,
   utc_str char(20),
   cgm int,
   utc datetime,
   et datetime
);

load data local infile 'dexcomutc.csv'
into table dexcom_cgm
fields terminated by ','
optionally enclosed by '"'
lines terminated by '\n'
ignore 1 lines;

update dexcom_cgm
set utc = str_to_date(utc_str, '%Y-%m-%d %T'),
et = addtime(utc,"4:00:00");

delete from dexcom_cgm where not (date(et) = '2022-08-11' and time(et) < '06:00');

select * from dexcom_cgm limit 10;
