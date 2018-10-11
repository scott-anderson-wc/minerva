#!/bin/bash

dir="$HOME/scott/devel/dumps"

filename=`date +${dir}/%F.sql`

if [ -e $filename ]; then
    filename=`date +${dir}/%F-%R.sql`
fi

mysqldump janice > $filename
ls -l $filename

