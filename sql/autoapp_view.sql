use autoapp;

-- the commands_extended_bolus_data and commads_dual_bolus_data tables are empty!
-- the commands_single_bolus_data is almost empty: 55 values
-- all the bolus data seems to be in bolus, but is there a connection with the commands table?
-- temp_basal table is empty


drop view if exists janice.command_view;
create view janice.command_view as
select command_id,
       created_timestamp,
       update_timestamp,
       type,
       if(commands.completed=1,"completed", "not completed") as completed,
       if(commands.error=1, "error", "") as error,
       state,
       ifnull(temp_basal.ratio,"") as ratio,
       ifnull(temp_basal.duration,"") as duration
from commands
     left outer join commands_temporary_basal_data as temp_basal using (command_id)
order by created_timestamp asc;     

drop view if exists janice.bolus_view;
create view janice.bolus_view as
select bolus_id,
       date,
       type,
       format(value,1) as value,
       duration
from bolus
order by date asc;

-- 10 columns. First three are universal: kind, id, date.
-- you can ignore id unless you want to look deeper in the other table
-- the next field is type, which is relevant for commands and boluses
-- the next several fields are only for commands: completed, error, and state
-- the ratio field is only relevant for temp basal commands
-- the value field is relevant for boluses and carbs
-- the duration field is relevant only for temp basal commands and extended boluses

drop view if exists janice.autoapp_view;
create view janice.autoapp_view as
select 'command' as 'kind',
       command_id as 'id',
       created_timestamp as 'date',
       update_timestamp,
       type,
       completed,
       error,
       state,
       ratio,
       "" as value,
       duration
from janice.command_view
union
select 'bolus' as 'kind',
       bolus_id as 'id',
       date,
       null,
       type,
       "" as completed,
       "" as error,
       "" as state,
       "" as ratio,
       value,
       duration
from janice.bolus_view
union
select 'carbs' as 'kind',
       carbohydrate_id as 'id',
       date,
       null,
       "" as type,
       "" as complete,
       "" as error,
       "" as state,
       "" as ratio,
       value,
       "" as duration
from carbohydrate       
order by date asc;
