-- testing the testing code

-- this is the loop_logic_test_test database;
use lltt; 

drop table if exists testing_command;
create table testing_command like loop_logic_test.testing_command;
insert into testing_command select * from loop_logic_test.testing_command;

drop table if exists realtime_cgm;
create table realtime_cgm like loop_logic_test.realtime_cgm;

drop table if exists source_cgm;
create table source_cgm like loop_logic.source_cgm;

insert into source_cgm values
(7, '2023-01-01 12:00:00', '2023-01-01 12:00:00', 100, 1, 1, 'NO'),
(7, '2023-01-01 12:05:00', '2023-01-01 12:05:00', 120, 2, 2, 'NO'),
(7, '2023-01-01 12:10:00', '2023-01-01 12:10:00', 140, 3, 3, 'NO'),
(7, '2023-01-01 12:15:00', '2023-01-01 12:15:00', 160, 4, 4, 'NO'),
(7, '2023-01-01 12:20:00', '2023-01-01 12:20:00', 180, 5, 5, 'NO');
