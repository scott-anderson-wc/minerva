#!/bin/bash

dir="$HOME/scott/devel/exports"

filename=`date +${dir}/ics-%F.csv`

if [ -e $filename ]; then
    filename=`date +${dir}/ics-%F-%R.csv`
fi

mysql -e 'select * from insulin_carb_smoothed;' > $filename
gzip $filename
du -h $filename.gz
