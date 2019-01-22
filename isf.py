'''Iterate over ICS2 and compute ISF values'''

import sys
import MySQLdb
import dbconn2
import csv
import itertools
from datetime import datetime, timedelta
import decimal                  # some MySQL types are returned as type decimal
from dbi import get_dsn, get_conn # connect to the database

def compute_isf():
    conn = get_conn()
    curs = conn.cursor(MySQLdb.cursors.DictCursor)
    curs.execute('''select rtime, total_bolus_volume from insulin_carb_smoothed_2 
                    where corrective_insulin = 1
                    and year(rtime) = 2018''')

    for row in curs.fetchall():
        start = row
        curs.execute('''select rtime,corrective_insulin,bg,cgm,total_bolus_volume 
                        from insulin_carb_smoothed_2
                        where rtime >= %s and rtime <= addtime(%s,'2:00')''',
                     [start['rtime'], start['rtime']])
        rows = curs.fetchall()
        first = rows[0]
        time = first['rtime'] 
        total_bolus = first['total_bolus_volume']
        startbg = first['cgm'] #default use cgm value for start 
        endbg = None  #default use cgm value for end 
        isf_trouble = None
        isf_round = None
        
        #if there is a bg value for the start use that 
        if(first['bg']):
            startbg = first['bg']
        if(rows[24]['bg']):
            endbg = rows[24]['bg'] 

        print len(rows)
        for r in rows:

            #check if there was corrective insulin given within 30min of start time
            if (r['corrective_insulin'] == 1 and r['rtime'] > start['rtime'] and r['rtime'] <= (start['rtime']+timedelta(minutes=30))):
                #if so, adjust the time and total bolus given 
                print 'extra insulin {} at time {}, earlier was {}'.format(r['total_bolus_volume'],r['rtime'],start['rtime'])
                time = r['rtime']
                total_bolus = total_bolus +  r['total_bolus_volume']

            #if there was corrective insulin given after 30min of start time, label as problem 
            if (r['corrective_insulin'] == 1 and r['rtime']> (start['rtime']+timedelta(minutes=30))):
                #only trouble if corrective insulin was given after 30min from start time and before 20min from 2hr mark (100min = 1hr40min)
                if( r['rtime'] < (start['rtime']+timedelta(minutes=100))): 
                    curs.execute('''UPDATE insulin_carb_smoothed_2 SET ISF_trouble = %s where rtime = %s''',['extra insulin',start['rtime']])
                    isf_trouble ='yes';
                else:
                    print 'ISF for {} has late insulin at {}'.format(start['rtime'],r['rtime'])
                    isf_round = True; 

            #if no bg value for start time, find one in within 10min of start time (?) 
            if (startbg == None and r['rtime'] <= (start['rtime'] + timedelta(minutes=10))):
                if (r['bg']):
                    startbg = r['bg']
                else:
                    startbg = r['cgm']
            if((r['rtime'] >= (start['rtime'] + timedelta(minutes=110))) and( r['cgm']or r['bg'])):
                if (r['bg']):
                    endbg = r['bg']
                else:
                    endbg =r['cgm']
                
            #print r
        if (endbg and startbg and isf_trouble == None):
            #compute isf
            isf = (startbg-endbg)/total_bolus
            print "ISF: ", isf
            #if extra insulin given after 1hr 40min, put isf value in different column 
            if (isf_round):
                curs.execute('''UPDATE insulin_carb_smoothed_2 SET ISF_rounded = %s where rtime = %s''',[isf, time])
            else: 
                curs.execute('''UPDATE insulin_carb_smoothed_2 SET isf = %s where rtime = %s''', [isf, time])
            curs.execute('''UPDATE insulin_carb_smoothed_2 SET ISF_trouble = %s where rtime = %s''',['ok', time])
        elif (endbg ==  None and startbg == None):
            curs.execute('''UPDATE insulin_carb_smoothed_2 SET ISF_trouble = %s where rtime = %s''', ['nobg', start['rtime']])
        #print "start: ", startbg, "end: ", endbg
        # check if any additional insulin given within 30 minutes of start -- done 
        # check if any additional insulin given later in that time range -- done
        # check if we have a CGM or BG value near the beginning of the range AND -- done 
        # check if we have a CGM or BG value near the end of the range -- done 
        # if we have *both* CGM and BG, take the BG
        # compute ISF based on starting and ending CGM or BG
        # update database using start (the primary key for ICS2)
        #raw_input('another?')


# added 12/13/2018 to avoid huge ISF values caused by tiny boluses
# not yet in use
min_bolus = 0.1                 

# this is the new implementation to compare with the old one that Mina did
# which sometimes computes *both* isf_rounded and isf, which seems weird to
# me -- Scott

def compute_isf_new(conn):
    curs = conn.cursor(MySQLdb.cursors.DictCursor)
    curs.execute('delete from isfcalcs') # make sure it is initially empty
    curs.execute('''select rtime from insulin_carb_smoothed_2 
                    where corrective_insulin = 1
                    and year(rtime) = 2018
                    and total_bolus_volume >= %s''',
                 [min_bolus])

    for row in curs.fetchall():
        start_time = row['rtime']
        print('start time: {}'.format(start_time))
        # added condition that isf_trouble is null, so that we can filter out
        # later rows, say that were merged or were outside grace periods and such
        curs.execute('''select rtime,corrective_insulin,bg,cgm,total_bolus_volume 
                        from insulin_carb_smoothed_2
                        where isf_trouble is null 
                        and rtime >= %s and rtime <= addtime(%s,'2:00')''',
                     [start_time, start_time])
        rows = curs.fetchall()
        first = rows[0]
        time = first['rtime'] 
        total_bolus = first['total_bolus_volume']
        startbg = first['cgm'] #default use cgm value for start 
        endbg = None  #default use cgm value for end 
        isf_trouble = None
        isf_round = None
        
        #if there is a bg value for the start use that. These might be None
        startbg = first['bg']
        endbg = rows[24]['bg'] 

        grace0 = start_time + timedelta(minutes=30)  # starting grace period
        grace1 = start_time + timedelta(minutes=100) # ending grace period
        for r in rows:

            #check if there was corrective insulin given within starting grace period
            if (r['corrective_insulin'] == 1 and
                start_time < r['rtime'] <= grace0):
                #if so, adjust the time and total bolus given 
                # time = r['rtime']   # no, just the total bolus
                total_bolus = total_bolus +  r['total_bolus_volume']
                curs.execute('''UPDATE insulin_carb_smoothed_2 SET ISF_trouble = %s where rtime = %s''',
                             ['grace0 insulin',r['rtime']])

            #if there was corrective insulin given after starting grace but before ending grace
            # label as problem 
            if (r['corrective_insulin'] == 1 and grace0 < r['rtime'] < grace1):
                curs.execute('''UPDATE insulin_carb_smoothed_2 SET ISF_trouble = %s where rtime = %s''',
                             ['non-grace insulin',r['rtime']])
                curs.execute('''UPDATE insulin_carb_smoothed_2 SET ISF_trouble = %s where rtime = %s''',
                             ['non-grace insulin at time {}'.format(r['time']),start_time])
                isf_trouble
                #only trouble if corrective insulin was given after 30min
                # from start time and before 20min from 2hr mark (100min = 1hr40min)
                if( r['rtime'] < (start['rtime']+timedelta(minutes=100))): 
                    isf_trouble ='yes';
                else:
                    isf_round = True; 

            #if no bg value for start time, find one in within 10min of start time (?) 
            if (startbg == None and
                r['rtime'] <= (start['rtime'] + timedelta(minutes=10))):
                startbg = r['bg'] or r['cgm']

            # similarly find endbg within 10 min of end time
            if((r['rtime'] >= (start['rtime'] + timedelta(minutes=110))) and
               ( r['cgm'] or r['bg'])):
                endbg = r['bg'] or r['cgm']
                
            #print r
        if (endbg and startbg and isf_trouble == None):
            #compute isf
            isf = (startbg-endbg)/total_bolus
            # print "ISF: ", isf
            #if extra insulin given after 1hr 40min, put isf value in different column 
            if (isf_round):
                curs.execute('''UPDATE insulin_carb_smoothed_2 SET ISF_rounded = %s where rtime = %s''',[isf, time])
            else: 
                curs.execute('''UPDATE insulin_carb_smoothed_2 SET isf = %s where rtime = %s''', [isf, time])
            curs.execute('''UPDATE insulin_carb_smoothed_2 SET ISF_trouble = %s where rtime = %s''',['ok', time])
            # New: record details of the calculation. [Scott 12/14/2019]
            curs.execute('''insert into isfcalcs(rtime,isf,bg0,bg1,bolus) 
                            values (%s,%s,%s,%s,%s)''',
                         [time, isf,startbg,endbg,total_bolus])
                            

        elif (endbg ==  None and startbg == None):
            curs.execute('''UPDATE insulin_carb_smoothed_2 SET ISF_trouble = %s where rtime = %s''', ['nobg', start['rtime']])

# ================================================================
# interface functions to md.py

def get_isf(rtime):
    conn = get_conn()
    curs = conn.cursor(MySQLdb.cursors.DictCursor)
    curs.execute('''SELECT rtime from insulin_carb_smoothed_2 
                    where corrective_insulin = 1 and rtime > %s''',
                 [rtime])
    start = curs.fetchone()['rtime']

    #get table from rtime
    curs.execute('''SELECT rtime, corrective_insulin, bg, cgm, total_bolus_volume,ISF,ISF_rounded,ISF_trouble 
                    from insulin_carb_smoothed_2 
                    where rtime>= %s and rtime<= addtime(%s,'2:00')''',
                 [start,start])
    return curs.fetchall()

def get_isf_next(conn,rtime):
    '''returns the next ISF value after the given rtime; 
this lets us implement the 'next" button'''
    curs = conn.cursor(MySQLdb.cursors.DictCursor)
    curs.execute('''SELECT rtime from insulin_carb_smoothed_2 
                    where corrective_insulin = 1 and rtime > %s''',
                 [rtime])
    return curs.fetchone()['rtime']

def get_isf_at(conn,rtime):
    curs = conn.cursor(MySQLdb.cursors.DictCursor)
    # in case rtime is not exact, find the first value that is >= to the given string
    curs.execute('''SELECT rtime from insulin_carb_smoothed_2 
                    where corrective_insulin = 1 and rtime >= %s''',
                 [rtime])
    start = curs.fetchone()['rtime']

    #get table from rtime
    curs.execute('''SELECT rtime, corrective_insulin, bg, cgm, total_bolus_volume,ISF,ISF_rounded,ISF_trouble 
                    from insulin_carb_smoothed_2 
                    where rtime>= %s and rtime<= addtime(%s,'2:00')''',
                 [start,start])
    return curs.fetchall()

def get_all_isf_plus_buckets():
    conn = get_conn()
    curs = conn.cursor()
    curs.execute('''SELECT isf from isfvals ''')
    allData = curs.fetchall()
    curs.execute('''select time_bucket(rtime),isf from isfvals''')
    bucketed = curs.fetchall()
    bucket_list = [ [ row[1] for row in bucketed if row[0] == b ]
                    for b in range(0,24,2) ]
    return(allData,bucket_list)

# new code to recompute ISF values from command line
if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: {} new/old'.format(sys.argv[0]))
    elif sys.argv[1] == 'new':
        conn = get_conn()
        compute_isf_new(conn)
    elif sys.argv[1] == 'old':
        compute_isf()
    else:
        print('Usage: {} new/old'.format(sys.argv[0]))
