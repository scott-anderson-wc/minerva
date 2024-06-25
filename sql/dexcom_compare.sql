use janice;

select 'our cgm';
select count(*) from our_cgm;
select our_et,our_cgm from our_cgm order by our_et;

select 'dexcom cgm';
select count(*) from dexcom_cgm;
select et,cgm from dexcom_cgm order by et;

select * from 
    (select our_et as et, 'ours', our_cgm from our_cgm
    union
    select et as et, 'dex', cgm from dexcom_cgm) as T
order by et asc;


-- select 'ours and theirs';
-- select time(our_et) as our_et,
-- time(et) as dexcom_edt,
-- our_cgm,
-- cgm
-- from our_cgm left join dexcom_cgm on(our_et=et);

-- select 'theirs and ours';
-- select time(our_et) as our_et,
-- time(et) as dexcom_edt,
-- our_cgm,
-- cgm
-- from dexcom_cgm left join our_cgm on(our_et=et);

