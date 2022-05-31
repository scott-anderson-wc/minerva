-- this table matches the data in est_isf_table.tsv which is the output from isf2.est_isf_table()

drop table if exists estimated_isf;
create table estimated_isf (
       year mediumint,          -- e.g. 2021
       quarter tinyint,         -- 1-4
       bucket tinyint,          -- 0-22
       isf float,               -- the median of the values we found
       how char(4),             -- computation option: A, A2, B, B2, C, C2, D, D2, and FAIL
       len tinyint,             -- number of values
       key (year,quarter,bucket) -- three-part key
);
load data local infile 'est_isf_table.tsv' into table estimated_isf
     fields terminated by '\t'
     lines terminated by '\n';
     
 
