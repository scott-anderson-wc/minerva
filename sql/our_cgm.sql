use janice;

drop table if exists our_cgm;
create table our_cgm (
   our_trend int,
   our_et datetime,
   our_utc datetime,
   our_cgm int
);

insert into our_cgm
select trend,dexcom_time,addtime(dexcom_time,"4:00:00"),mgdl
from realtime_cgm2
where date(rtime) = '2022-08-11' and time(rtime) < '06:00' and mgdl is not null;

select count(*) from our_cgm;
select * from our_cgm limit 10;
