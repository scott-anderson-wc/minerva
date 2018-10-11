#!/bin/bash

# script to run when new data from Dexcom etc is uploaded. Does the pre-processing to
# create the derived _2 tables and resolve duplicates.

dir="$HOME/scott/devel/pre-process/logs"
log=`date +${dir}/reprocess.log.%F`

if [ -e $log ]; then
    log=`date +${dir}/reprocess.log.%F-%R`
fi

touch $log

echo "logfile is $log"
echo "delete bogus insulin_carb and cgm data, making _1 tables, and coercing datatypes" | tee >> $log
mysql < process_1.sql >> $log
echo "make rtime values and basal_gap fields in insulin_carb and cgm, making _2 tables" | tee >> $log
mysql < process_2.sql >> $log
echo "identify basal gaps (no change for 24 hours)"
./no-basal-changes.py update
echo "basal changes fix"
mysql -e "UPDATE insulin_carb_2 SET basal_gap = 0 WHERE rec_num = 87991;"
echo "fix the funky off-by-one-day error" | tee >> $log
mysql -e "UPDATE insulin_carb_2 SET date_time = date_add(date_time,interval 1 day) WHERE '2016-04-01 21:25' <= date_time and date_time <= '2016-05-02 18:21';"
echo "groups and deal with duplicates" | tee >> $log
mysql < dup-cgm-readings-rtimes.sql >> $log
mysql < dup-mgm-readings-rtimes.sql >> $log
echo "identify duplicates in insulin_carb." | tee >> $log
mysql < dup-insulin_carb-entries.sql >> $log
echo "make ICS" | tee >> $log
mysql < ../sql/make-insulin_carb_smoothed.sql >> $log
# insulin_carb_smoothed is now made, but empty. It's filled using dynamic_insulin:
python ../dynamic_insulin.py 
./export-ICS2-to-TSV.sh
