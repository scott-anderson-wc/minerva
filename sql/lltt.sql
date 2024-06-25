-- replicate some tables in loop_logic for testing autoapp_to_loop_logic

use lltt;

drop table if exists loop_summary;
create table loop_summary like loop_logic.loop_summary;

-- some carbs from this month

insert into loop_summary
select * from loop_logic.loop_summary
where carb_value > 0 and carb_timestamp > '2023-03-01';

