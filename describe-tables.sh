#!/bin/bash

out=table-description.text
if [ -e $out ]; then
    rm $out
    touch $out
fi

# order is important. the -t has to be first
mysql -te "describe insulin_carb;" | cat >> $out
mysql -te "select 'insulin_carb range', min(epoch), max(epoch) from insulin_carb" >> $out
mysql -te "describe cgm;" >> $out
mysql -te "select 'cgm range',min(epoch), max(epoch) from cgm" >> $out
