drop table if exists scott_test;
create table scott_test (
    date_time datetime,
    mgdl      varchar(4)
    );

insert into scott_test values
('1980-01-01 12:00:00', '100'),
('1980-01-01 15:00:00', '110'),
('1980-01-02 04:00:00', '120');

select 'all data',date_time,mgdl from scott_test;

select concat(A.date_time,' - ',B.date_time), timediff(B.date_time,A.date_time)
from scott_test as A, scott_test as B
where A.date_time < B.date_time;

select 'starts long gap',A.date_time from scott_test as A, scott_test as B
where A.date_time < B.date_time and timediff(B.date_time,A.date_time) < '12:00:00';
