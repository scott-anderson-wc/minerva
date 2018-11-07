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
    curs.execute('''select rtime, total_bolus_volume from insulin_carb_smoothed_2 
                    where corrective_insulin = 1
                    and year(rtime) = 2018''')

    for row in curs.fetchall():
        start = row
        curs.execute('''select rtime,corrective_insulin,bg,cgm,total_bolus_volume 
                        from insulin_carb_smoothed_2
                        where rtime >= %s and rtime <= addtime(%s,'2:00')''',
                     [start[0], start[0]])
        rows = curs.fetchall()
        first = rows[0]
        time = first[0] 
        total_bolus = first[4]
        startbg = first[3] #default use cgm value for start 
        endbg = None  #default use cgm value for end 
        isf_trouble = None
        
        #if there is a bg value for the start use that 
        if(first[2]):
            startbg = first[2]
        if(rows[24][2]):
            endbg = rows[24][2] 

        print len(rows)
        for r in rows:

            #check if there was corrective insulin given within 30min of start time
            if (r[1] == 1 and r[0] > start[0] and r[0] <= (start[0]+timedelta(minutes=30))):
                #if so, adjust the time and total bolus given 
                time = r[0]
                total_bolus = total_bolus +  r[4]

            #if there was corrective insulin given after 30min of start time, label as problem 
            if (r[1] == 1 and r[0]> (start[0]+timedelta(minutes=30))):
                curs.execute('''UPDATE insulin_carb_smoothed_2 SET ISF_trouble = %s where rtime = %s''',['yes',start[0]])
                isf_trouble ='yes'; 

            #if no bg value for start time, find one in within 10min of start time (?) 
            if (startbg == None and r[0] <= (start[0] + timedelta(minutes=10))):
                if (r[2]):
                    startbg = r[2]
                else:
                    startbg = r[3]
            if((r[0] >= (start[0] + timedelta(minutes=110))) and( r[3]or r[2])):
                if (r[2]):
                    endbg = r[2]
                else:
                    endbg =r[3]
                
            print r
        if (endbg and startbg and isf_trouble == None):
            #compute isf
            isf = (startbg-endbg)/total_bolus
            print "ISF: ", isf
            curs.execute('''UPDATE insulin_carb_smoothed_2 SET isf = %s where rtime = %s''', [isf, time])
        else:
            curs.execute('''UPDATE insulin_carb_smoothed_2 SET ISF_trouble = %s where rtime = %s''', ['yes', start[0]])
        print "start: ", startbg, "end: ", endbg
        # check if any additional insulin given within 30 minutes of start -- done 
        # check if any additional insulin given later in that time range -- done
        # check if we have a CGM or BG value near the beginning of the range AND -- done 
        # check if we have a CGM or BG value near the end of the range -- done 
        # if we have *both* CGM and BG, take the BG
        # compute ISF based on starting and ending CGM or BG
        # update database using start (the primary key for ICS2)
        raw_input('another?')

