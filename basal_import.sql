use autoapp;

-- select 'bh', date, value, null from basal_hour;
-- select 's', date, null, if(value=0,0,1) from suspend;

select 'bh' as 'table',
       date,
       value as 'bh_value',
       null as 'tb_going',
       null as 'tb_percent',
       null as 'tb_seconds',
       null as 'su_value'
from basal_hour
limit 10;

select 'tb' as 'table',
        date,
        null as 'bh_value',
        if(temp_basal_in_progress=0,0,1) as 'tb_going',
        temp_basal_percent as 'tb_percent',
        temp_basal_total as 'tb_seconds',
        null as 'su_value'
from temp_basal_state
limit 10;

select 'su' as 'table',
       date,
       null as 'bh_value',
       null as 'tb_going',
       null as 'tb_percent',
       null as 'tb_seconds',
       if(value=0,0,1) as 'su_value'
from suspend
limit 10;

select 'bh' as 'table',
       date,
       value as 'bh_value',
       null as 'tb_going',
       null as 'tb_percent',
       null as 'tb_seconds',
       null as 'su_value'
from basal_hour
union all
select 'tb' as 'table',
        date,
        null as 'bh_value',
        if(temp_basal_in_progress=0,0,1) as 'tb_going',
        temp_basal_percent as 'tb_percent',
        temp_basal_total as 'tb_seconds',
        null as 'su_value'
from temp_basal_state
union all
select 'su' as 'table',
       date,
       null as 'bh_value',
       null as 'tb_going',
       null as 'tb_percent',
       null as 'tb_seconds',
       if(value=0,0,1) as 'su_value'
from suspend
order by date;
