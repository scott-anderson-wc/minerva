# this file regularizes the date fields and formats, so that
# both insulin_carb_2 and cgm_2 have `date_time` as the standard field
# with a datetime datatype.

# This script works because bogus values have already been removed and the
# remaining data is such that one field can act as the master. If that
# were not the case, we would need to use something more flexible like
# Python.

# This takes only a few seconds.

use janice;

# the following makes it idempotent

delete from insulin_carb_2;

insert into insulin_carb_2(
       user,date_time,
       Basal_amt,temp_basal_down,temp_basal_up,temp_basal_duration,
       bolus_type,bolus_volume,
       Immediate_percent, extended_percent,
       duration,
       carbs,
       notes,
       rec_num)
select 
       user,str_to_date(date_time,'%Y%m%d%H%i'),
       Basal_amt,temp_basal_down,temp_basal_up,temp_basal_duration,
       bolus_type,bolus_volume,
       Immediate_percent, extended_percent,
       duration,
       carbs,
       notes,
       rec_num
 from insulin_carb_1;

# can now drop insulin_carb_1;

delete from cgm_2;
insert into cgm_2(user,date_time,mgdl,rec_num)
select user, str_to_date(time,'%m/%d/%Y %H:%i'), mgdl, rec_num
from cgm_1;

