'''Iterate over ICS2 and compute ISF values'''

import MySQLdb
import dbconn2
import csv
import itertools
from datetime import datetime, timedelta
import decimal                  # some MySQL types are returned as type decimal
from dbi import get_dsn, get_conn # connect to the database

def compute_isf():
    conn = get_conn()
    curs = conn.cursor()
    curs.execute('''select rtime from insulin_carb_smoothed_2 
                    where corrective_insulin = 1
                    and year(rtime) = 2018''')
    for row in curs.fetchall():
        start = row
        curs.execute('''select rtime,corrective_insulin,bg,cgm 
                        from insulin_carb_smoothed_2
                        where rtime >= %s and rtime <= addtime(%s,'2:00')''',
                     [start, start])
        rows = curs.fetchall()
        print len(rows)
        for r in rows:
            print r
        # check if any additional insulin given within 30 minutes of start
        # check if any additional insulin given later in that time range
        # check if we have a CGM or BG value near the beginning of the range AND
        # check if we have a CGM or BG value near the end of the range
        # if we have *both* CGM and BG, take the BG
        # compute ISF based on starting and ending CGM or BG
        # update database using start (the primary key for ICS2)
        raw_input('another?')

