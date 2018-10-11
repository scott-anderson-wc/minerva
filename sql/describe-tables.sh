#!/bin/bash

out=table-description.text
if [ -e $out ]; then
    rm $out
    touch $out
fi

# order is important. the -t has to be first
for table in cgm cgm_1 cgm_2 insulin_carb insulin_carb_1 insulin_carb_2 insulin_carb_smoothed ics
do
    echo "description of $table" >> $out
    mysql -te "describe $table;" | cat >> $out
done

