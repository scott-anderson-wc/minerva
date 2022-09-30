#!/bin/bash

cd ~/llconf/

dump=`date +dump-%F.sql`
mysqldump loop_logic configuration mode glucose_range datetime_program > $dump

mysql -e 'select * from loop_logic.configuration;' > configuration.tsv;
mysql -e 'select * from loop_logic.mode;' > mode.tsv
mysql -e 'select * from loop_logic.glucose_range;' > glucose_range.tsv
mysql -e 'select * from loop_logic.datetime_program;' > datetime_program.tsv

