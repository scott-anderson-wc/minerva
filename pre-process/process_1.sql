# I am going to adopt the protocol that tables with names ending in a digit are processed versions
# and ones without are the original raw data

use janice;

# The first ones just delete bogus rows.

drop table if exists `insulin_carb_1`;
CREATE TABLE `insulin_carb_1` like `insulin_carb`;

insert into insulin_carb_1 (select * from `insulin_carb`);

delete from insulin_carb_1 where
date_time = '' and
Basal_amt = '' and
temp_basal_down = '' and
temp_basal_up = '' and
temp_basal_duration = '' and
bolus_type = '' and
bolus_volume = '' and
Immediate_percent = '' and
extended_percent = '' and
duration = '' and
carbs = '' and
notes = '';

# Next, I learned that there are some early rows where date and date_time
# are both the empty string and epoch is zero. There are only 10 such, and all
# before May 18, 2014. Witness:

select 'rows missing date info', count(*) from insulin_carb_1
where date = '' and date_time = '' and epoch_time = '0';

select 'max rec_num with missing date info', max(rec_num) from insulin_carb_1
where date = '' and date_time = '' and epoch_time = '0';

select rec_num,date_time from insulin_carb_1
where rec_num >= 390 and rec_num <= 395;

# So, I am deleting those early data:

delete from insulin_carb_1 where rec_num < 395;

drop table if exists `cgm_1`;

create table `cgm_1` like `cgm`;

insert into cgm_1 (select * from cgm);

delete from cgm_1 where
mgdl = '';
