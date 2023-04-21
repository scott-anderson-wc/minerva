import os                       # for path.join
import sys
import math                     # for floor
import collections              # for deque
import cs304dbi as dbi
from datetime import datetime, timedelta
import date_ui
import logging

## This file is no good. The callproc doesn't work and I found a good
## SQL algorithm in closest_time.sql

HUGH_USER_ID = 7

def closest_time(conn, database, target_timestamp):
    curs = dbi.cursor(conn)
    query = f'''SELECT cgm_id, user_id, trend, dexcom_timestamp_utc, cgm_value 
               FROM {database}.realtime_cgm
               WHERE user_id = %s AND 
               abs(unix_timestamp(dexcom_timestamp_utc) - unix_timestamp(%s)) =
                  (select min( abs(unix_timestamp(dexcom_timestamp_utc) - unix_timestamp(%s)) )
                          from {database}.realtime_cgm)'''
    output = 0
    # curs.callproc('closest_cgm', [HUGH_USER_ID, target_timestamp, 30*60, output ])

    q1 = f'''select min(abs( unix_timestamp(dexcom_timestamp_utc) - unix_timestamp(%s)))
             from {database}.realtime_cgm
             where user_id = %s 
               and (abs( unix_timestamp(dexcom_timestamp_utc) - unix_timestamp(%s))) < %s'''
    curs.execute(q1, [target_timestamp, HUGH_USER_ID, target_timestamp, 30*60])
    row = curs.fetchone()
    print(row[0])

def c2(target_timestamp):
    conn = dbi.connect()
    curs = conn.cursor()
    output = 0
    curs.callproc('loop_logic.closest_cgm', [HUGH_USER_ID, target_timestamp, 30*60, output ])
    print('output', output)
    


    # target = date_ui.to_datetime(target_time)
    # posix = target.timestamp()  # a float, seconds since the epoch
    # nr = curs.execute(query2, [HUGH_USER_ID, target_timestamp, 30*60])
    # print(nr)
    # return curs.fetchone()

    
                      
