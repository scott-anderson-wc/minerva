-- I created this table to hold estimated ISF values
-- as computed by isf_at_time in isf2.py

drop table if exists isf_est;
create table isf_est(
    year    char(4),
    quarter char(1),
    time_bucket char(2),
    isf_est float,
    how char(2),
    n tinyint,
    primary key (year,quarter,time_bucket)
);

-- this tsv file captured by the output of isf_est_table in isf2.py
load data local infile 'isf_est_table.tsv' into table isf_est;

