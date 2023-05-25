use autoapp_scott;

create table dana_history_timestamp like autoapp.dana_history_timestamp;
create table bolus like autoapp.bolus;
create table carbohydrate like autoapp.carbohydrate;
create table commands like autoapp.commands;
create table commands_single_bolus_data like autoapp.commands_single_bolus_data;
create table commands_temporary_basal_data like autoapp.commands_temporary_basal_data;

insert into dana_history_timestamp select * from autoapp.dana_history_timestamp;

use loop_logic_scott;

create table migration_status like loop_logic.migration_status;
create table testing_command like loop_logic.testing_command;
create table source_cgm like loop_logic.source_cgm;
create table realtime_cgm like loop_logic.realtime_cgm;
create table loop_summary like loop_logic.loop_summary;
create table configuration like loop_logic.configuration;

insert into migration_status select * from loop_logic.migration_status;

insert into configuration select * from loop_logic.configuration;

