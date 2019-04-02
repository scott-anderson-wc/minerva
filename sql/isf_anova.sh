#!/bin/bash

# This writes out data from the isf_details table
# to analyze with ANOVA
# to determine whether
# 1. post 2016 is different from not
# 2. starting bg > 200 is different from not
# while acknowledging that time_bucket does matter

csv_file=isf-split-by-2016.csv
if [ -e "$csv_file" ]; then
    rm $csv_file
fi
query=`cat <<EOF
select year(rtime)>2016,time_bucket(rtime) as bucket,isf
from isf_details
order by year(rtime)>2016, time_bucket(rtime)
EOF`
echo $query | mysql > $csv_file

csv_file=isf-split-by-bg0.csv
if [ -e "$csv_file" ]; then
    rm $csv_file
fi
query=`cat <<EOF
select bg0>200,time_bucket(rtime) as bucket,isf
from isf_details
order by bg0>200, time_bucket(rtime)
EOF`
echo $query | mysql > $csv_file

