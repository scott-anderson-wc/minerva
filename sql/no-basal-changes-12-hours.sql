-- no change to basal value in 12 hours
-- return rows where there exists no row where
-- there is a different basal value and
-- the later row is less than 12 hours away

-- don't run this; too slow!

exit;

drop table if exists cgm_3;
create table cgm_3 like cgm_2;

insert into cgm_3
(select * from cgm_2);

select count(*) from cgm_3;

select * from cgm_3 A where
not exists (select * from cgm_3 B where B.mgdl is not NULL
    	   	     	            and B.mgdl <> A.mgdl
				    and A.date_time < B.date_time
				    and timediff(B.date_time, A.date_time) < '12:00:00');
