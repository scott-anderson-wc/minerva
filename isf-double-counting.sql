-- determine whether insulin in the middle also counts as insulin before for the next report
-- outcome: it does, so we are double-counting in a way

drop table if exists isf2;
create table isf2 (
    rtime datetime,
    isf_trouble varchar(50)
    );

insert into isf2
select rtime,isf_trouble
from insulin_carb_smoothed_2
where isf_trouble = 'insulin in middle' or isf_trouble = 'insulin before';

select count(*) from isf2;

select a.rtime,a.isf_trouble,b.rtime,b.isf_trouble from isf2 as a, isf2 as b
where a.isf_trouble = 'insulin in middle'
and b.isf_trouble = 'insulin before'
and a.rtime < b.rtime and b.rtime < addtime(a.rtime,'1:40');

drop table isf2;
