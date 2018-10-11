#!/bin/bash

days=`mysql -B --skip-column-names <<EOF
select ymd as yyyy_mm_dd
from (
select date(date_time) as ymd, sum(carbs) as carbsum
from insulin_carb_2
group by date(date_time)
) as a inner join (
select date(rtime) as ymd, sum(carbs) as carbsum
from insulin_carb_smoothed
group by date(rtime)
) as b using (ymd)
where (a.carbsum-b.carbsum) <> 0;
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
    origsum=`mysql --skip-column-names -B -e "select round(sum(carbs)) from insulin_carb_2 where date(date_time) = '$day';"`
    # echo "sum1 is $origsum"
    smoothsum=`mysql --skip-column-names -B -e "select round(sum(carbs)) from insulin_carb_smoothed where date(rtime) = '$day';"`
    # echo "sum2 is $smoothsum"
    # echo "$origsum and $smoothsum"
    let "diff = $origsum - $smoothsum"
    echo "$i/$n difference on $day ($origsum vs $smoothsum) or $diff"
    echo "original data first:"
    mysql -e "select date_time, round(carbs) as carbs from insulin_carb_2 where date(date_time) = '$day' and carbs > 0;"
    echo "smoothed data:"
    mysql -e "select rtime, carbs from insulin_carb_smoothed where date(rtime) = '$day' and carbs > 0;"
    echo "next?"
    read ans
done
