#!/bin/bash

# This writes out data from the isf_details
# table to determine whether
# 1. post 2016 is different from not
# 2. starting bg > 200 is different from not

file=isf-split-by-2016.csv
if [ -e "$file" ]; then
    rm $file
fi
mysql -e <<EOF
select year(rtime)>2016,time_bucket(rtime) as bucket,isf
from isf_details
order by year(rtime)>2016, time_bucket(rtime)
EOF
