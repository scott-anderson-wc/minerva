#!/bin/bash

# script to check on whether realtime_cgm data is migrating properly
# from janice.realtime_cgm2 to loop_logic*.realtime_cgm

mysql <<EOF
select * from janice.realtime_cgm2
where dexcom_time > current_timestamp - interval 1 hour;

select * from janice.realtime_cgm2
where dexcom_time > current_timestamp - interval 1 hour;

select * from janice.realtime_cgm2
where dexcom_time > current_timestamp - interval 1 hour;
EOF

