-- see notes in predictive_model_june21.py

drop table if exists insulin_action_curve;
create table insulin_action_curve (
       user varchar(30),
       curve_date timestamp,
       -- 60 values times 13 digits each, plus commas and spaces and square brackets
       curve varchar(1000),
       notes text);

describe insulin_action_curve;


       
       
