alter table insulin_carb_smoothed_2 drop column ISF_trouble;
alter table insulin_carb_smoothed_2 add column ISF_trouble varchar(50) after ISF;
