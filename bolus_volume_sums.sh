#!/bin/bash

days=`mysql -B --skip-column-names <<EOF
select ymd as yyyy_mm_dd
from (
select date(date_time) as ymd, sum(bolus_volume) as bv_sum
from insulin_carb_2
group by date(date_time)
) as a inner join (
select date(rtime) as ymd, sum(bolus_volume) as bv_sum
from insulin_carb_smoothed
group by date(rtime)
) as b using (ymd)
where (a.bv_sum-b.bv_sum) > 0.001 or (b.bv_sum-a.bv_sum) > 0.001
EOF`

n=0
for day in $days; do
    let n++
done

echo "Disagreements on $n days"

# echo "days is $days"

i=1
for day in $days; do
    if [ "$day" = 'yyyy_mm_dd' ]; then
	continue
    fi
    origsum=`mysql --skip-column-names -B -e "select sum(bolus_volume) from insulin_carb_2 where date(date_time) = '$day';"`
    smoothsum=`mysql --skip-column-names -B -e "select round(sum(bolus_volume),2) from insulin_carb_smoothed where date(rtime) = '$day';"`
    # echo "$origsum and $smoothsum"
    diff=`perl -e "print $origsum - $smoothsum;"`
    echo "$i/$n difference on $day ($origsum vs $smoothsum) or $diff"
    echo "original data first:"
    mysql -e "select date_time, bolus_volume from insulin_carb_2 where date(date_time) = '$day' and bolus_volume > 0;"
    echo "smoothed data:"
    mysql -e "select rtime, round(bolus_volume,2) as bolus_volume from insulin_carb_smoothed where date(rtime) = '$day' and bolus_volume > 0;"
    echo "next?"
    read ans
done
