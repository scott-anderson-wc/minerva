mysql -e 'SELECT date(epoch),count(*) from cgm group by date(epoch)' | \
    awk '{printf("\"%s\",%s\n", $1, $2); }' > count-cgm-by-date.csv

