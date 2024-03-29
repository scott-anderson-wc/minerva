#!/bin/bash

dir="$HOME/scott/devel3/exports"

filename=`date +${dir}/ics2-%F.csv`

if [ -e $filename ]; then
    filename=`date +${dir}/ics2-%F-%R.csv`
fi

mysql -e 'select * from insulin_carb_smoothed_2;' > $filename
gzip $filename
du -h $filename.gz
