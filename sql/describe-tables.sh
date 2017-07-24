#!/bin/bash

out=table-description.text
if [ -e $out ]; then
    rm $out
    touch $out
fi

# order is important. the -t has to be first
mysql -te "describe insulin_carb_2;" | cat >> $out
mysql -te "describe cgm_2;" >> $out
