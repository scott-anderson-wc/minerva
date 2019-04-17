
'''Iterate over ICS2 and compute ISF values'''

'''This newer version attempts to be more clear about the different criteria

1. There's a 30-minute window at the beginning of the 2-hour span for
ISF calculations. Any boluses in that 30 minute window are summed, and the 
last time is used for determining the beginning of the 2-hour span. 

2. There should be no bolus of any kind (corrective or not) within the
first 100" of the time interval (20 minutes from the end). This is
measured from the time of the last bolus in the beginning period.

3. The bolus should not be too small; it should be >= global variable min_bolus. 

4. If there is a bolus in the last 20 minutes, this allowed, but the
ISF value is stored in ISF_rounded instead of ISF.

Implemented by Scott 1/22/2019

'''


import MySQLdb
import dbconn2
import csv
import math
import itertools
from datetime import datetime, timedelta,date
import decimal                  # some MySQL types are returned as type decimal
from dbi import get_dsn, get_conn # connect to the database
import date_ui

# added 12/13/2018 to avoid huge ISF values caused by tiny boluses
# In her email of 12/17/2018, Janice described several problematic
# calculations based on small boluses. Said bolus should be >= 0.35

min_bolus = 0.35

def get_window(curs,start_time):
    curs.execute('''select rtime,corrective_insulin,bg,cgm,total_bolus_volume 
                    from insulin_carb_smoothed_2
                    where rtime >= %s and rtime <= addtime(%s,'2:30')''',
                 [start_time, start_time])
    rows = curs.fetchall()
    return rows

def any_bolus_in_time_span(conn,start,end):
    curs = conn.cursor()
    curs.execute('''select count(*) from insulin_carb_smoothed_2 
                    where total_bolus_volume > 0
                    and %s <= rtime and rtime <= %s''',
                 [date_ui.python_datetime_to_mysql_datetime(start),
                  date_ui.python_datetime_to_mysql_datetime(end)])
    result = curs.fetchone()
    return result[0] > 0


# a time when this happens is 2018-02-02 00:45:00 and 00:50:00

def bolus_sum_during_start(rows, t2):
    t3 = t2
    bolus_sum = 0
    bolus_count = 0
    end_time = t2 + timedelta(minutes=30)
    # print 'end_time',end_time
    for row in rows:
        # print row['rtime'], row['total_bolus_volume']
        if row['rtime'] == end_time:
            if bolus_count > 2:
                print 'summed {} corrections!!'.format(bolus_count)
            return bolus_sum, t3
        tbv = row['total_bolus_volume'] 
        if tbv > 0: 
            bolus_count += 1
            bolus_sum += tbv
            t3 = row['rtime']
    raise Exception('this should not happen')

def boluses_in_time_range(rows, start, end):
    for row in rows:
        time = row['rtime']
        if start <= time <= end and row['total_bolus_volume'] > 0:
            return True
    return False

def bg_at_time(rows, time):
    '''search for the first non-empty BG (preferred) or CGM (acceptable) value from a row 
whose time is equal to or within 10 minutes of the given time. Returns None if none found.'''
    start = time
    end   = time+timedelta(minutes=10)
    for row in rows:
        row_time = row['rtime']
        if start <= row_time <= end:
            if row['bg']:
                return row['bg']
            if row['cgm']:
                return row['cgm']
    # raise Exception('Never found a useable BG or CGM value')
    return None

def bg_at_time_extended(rows,time):
    '''search for the first non-empty BG (preferred) or CGM (acceptable) vaue from a row
whose time is within 10min before or 45min after the given time. Returns None if none
found'''
    base_index = 0
    for r in rows:
        if r['rtime'] == time:
            break
        base_index += 1
    for delta in [0,1,-1,2,-2,3,4,5,6,7,8,9]:
        row = rows[base_index + delta]
        if row['bg']: 
            return row['bg']
        if row['cgm']:
            return row['cgm']
    return None 
    
def get_bg_time_window(curs, time):
    '''retrieve data from 10 min before to 45min after the given time ''' 
    start_time = time - timedelta(minutes=10)
    curs.execute('''select rtime, corrective_insulin, bg,cgm, total_bolus_volume from
    insulin_carb_smoothed_2 where rtime >= %s and rtime<=addtime(%s,'0:45')''',
                 [start_time,time])
    rows = curs.fetchall()
    return rows

def compute_isf():
    conn = get_conn()
    curs = conn.cursor(MySQLdb.cursors.DictCursor)
    curs.execute('update insulin_carb_smoothed_2 SET ISF_trouble = null, isf = null, ISF_rounded = null')
    curs.execute('delete from isfvals') # make sure table is initially empty
    curs.execute('delete from isf_details') # make sure table is initially empty
    curs.execute('''select rtime, total_bolus_volume from insulin_carb_smoothed_2 
                    where corrective_insulin = 1 ''')
                   # and year(rtime) = 2018''')
    rows = curs.fetchall()

    # some stats
    total = len(rows)
    skipped_before = 0 # events skipped because of insulin in BEFORE period
    skipped_small = 0  # events skipped because bolus too small
    skipped_middle = 0 # events skipped because bolus during MIDDLE period
    skipped_nobg_beg = 0   # events skipped because start or end BG value missing (or both)
    skipped_nobg_end = 0
    good_isf = 0       # events with good ISF value 
    insulin_before = 0 #events with insulin 4 hours prior to the event 
    
    for row in rows:
        start = row
        t2 = start['rtime']
        t1 = t2 - timedelta(minutes=100)

        prior_insulin = any_bolus_in_time_span(conn, t2 - timedelta(hours=4),t1)

        if any_bolus_in_time_span(conn, t1,t2 - timedelta(minutes=5)):
            # print 'skipping {} because of insulin in the BEFORE period: {} to {}'.format(t2,t1,t2)
            skipped_before += 1
            curs.execute('''UPDATE insulin_carb_smoothed_2 SET ISF_trouble = %s where rtime = %s''',
                         ['insulin before', t2])
            continue

        # get values for the next 2:30 (worst case scenario)
        rows = get_window(curs, start['rtime'])

        # Sum the boluses in the first 30 minutes
        bolus_sum, t3 = bolus_sum_during_start(rows,t2)
        if t3 != t2:
            # this is just informational. Can be deleted
            # print 'boluses in beginning from {} to {} sum to {}'.format(t2,t3,bolus_sum)
            pass

        if bolus_sum < min_bolus:
            # print 'bolus sum {} is too small; skipping {}'.format(bolus_sum,t3)
            curs.execute('''UPDATE insulin_carb_smoothed_2 SET ISF_trouble = %s where rtime = %s''',
                         ['bolus too small', t3])
            skipped_small += 1
            continue
        
        # from now on, use t3 rather than t2, particularly for looking up BG
            
        t4 = t3 + timedelta(minutes=100)
        t5 = t4 + timedelta(minutes=20)

        # Check for no boluses in middle time
        if boluses_in_time_range(rows, t3+timedelta(minutes=5), t4-timedelta(minutes=5)):
            # print 'skipping {} because of insulin in the middle period'.format(t3)
            skipped_middle += 1
            curs.execute('''UPDATE insulin_carb_smoothed_2 SET ISF_trouble = %s where rtime = %s''',
                         ['insulin in middle', t3])
            if t2 != t3:
                curs.execute('''UPDATE insulin_carb_smoothed_2 SET ISF_trouble = %s where rtime = %s''',
                             ['insulin in middle', t2])
            continue

        # Check whether there were boluses in end time
        boluses_in_end = boluses_in_time_range(rows, t4, t5)
        #boluses_in_time_range(rows, t4+timedelta(minutes=5), t5)
        if boluses_in_end:
            # print 'insulin in the end period: {} to {}'.format(t4,t5)
            pass
            
        # Okay, ready for calculation.
        bg_at_t3 = bg_at_time(rows, t3)
        bg_rows = get_bg_time_window(curs,t5)
        bg_at_t5 = bg_at_time_extended(bg_rows,t5)
        if bg_at_t3 and bg_at_t5:
            if prior_insulin:
                insulin_before += 1
            isf = (bg_at_t3 - bg_at_t5) / bolus_sum
            #print 'isf {} to {} => ( {} - {} ) / {} => {:.2f} '.format(t3,t5,bg_at_t3, bg_at_t5, bolus_sum, isf)
            good_isf += 1
            if boluses_in_end:
                curs.execute('''UPDATE insulin_carb_smoothed_2 SET ISF_trouble = %s, ISF_rounded = %s where rtime = %s''',
                             ['insulin at end', isf, t3])
            else: 
                curs.execute('''UPDATE insulin_carb_smoothed_2 SET isf = %s where rtime = %s''', [isf, t3])
            # New: record details of the calc in the isfvals table. [Scott 12/13/2019]
            #curs.execute('''insert into isf_details(rtime,isf,bg0,bg1,bolus) values (%s,%s,%s,%s,%s)''',
                        # [t3, isf, bg_at_t3, bg_at_t5, bolus_sum])
            curs.execute('''insert into isf_details(rtime,isf,bg0,bg1,bolus,prior_insulin) values (%s,%s,%s,%s,%s,%s)''',[t3,isf,bg_at_t3,bg_at_t5, bolus_sum,prior_insulin])
        else:
            #skipped_bg += 1
            skipped = False  
            if not bg_at_t3:
                skipped_nobg_beg += 1
                skipped = True
                curs.execute('''UPDATE insulin_carb_smoothed_2 set ISF_trouble = %s where rtime = %s''',
                             [ 'nobg', t3]) # 'missing start BG value'
            if not bg_at_t5 and not skipped:
                skipped_nobg_end += 1
                #print 'nobg at end', t3
                curs.execute('''UPDATE insulin_carb_smoothed_2 set ISF_trouble = %s where rtime = %s''',
                             [ 'nobg', t3]) # 'missing end BG value'
        #print "start: ", startbg, "end: ", endbg
        # check if any additional insulin given within 30 minutes of start -- done 
        # check if any additional insulin given later in that time range -- done
        # check if we have a CGM or BG value near the beginning of the range AND -- done 
        # check if we have a CGM or BG value near the end of the range -- done 
        # if we have *both* CGM and BG, take the BG
        # compute ISF based on starting and ending CGM or BG
        # update database using start (the primary key for ICS2)
        #raw_input('another?')
    # end of loop
    print '''There were {} corrective insulin events from 2014 -  2018. 
{} events were skipped because of insulin before the START period
{} events were skipped because the bolus was too small
{} events were skipped because there was a bolus in the MIDDLE period
{} events were skipped because start BG was not available, 
{} events were skipped because end BG was not available, leaving
{} events with a good ISF and 
{} good events with insulin within 4 hours before event 
{} skipped + {} good is {} total.'''.format(total, skipped_before, skipped_small, skipped_middle, skipped_nobg_beg,skipped_nobg_end,good_isf,insulin_before,
                                            (skipped_before + skipped_small + skipped_middle + skipped_nobg_beg + skipped_nobg_end),
                                            good_isf,total)
                                            

def get_first_corrective_insulin(year=2018):
    conn = get_conn()
    curs = conn.cursor(MySQLdb.cursors.DictCursor)
    curs.execute('''SELECT min(rtime) as rtime from insulin_carb_smoothed_2 
where corrective_insulin = 1 and year(rtime) = %s''',
                 [year])
    start = curs.fetchone()['rtime']
    return start

def get_isf(rtime):
    conn = get_conn()
    curs = conn.cursor(MySQLdb.cursors.DictCursor)
    curs.execute('''SELECT rtime from insulin_carb_smoothed_2  where corrective_insulin = 1 and rtime > %s''',[rtime])
    start = curs.fetchone()['rtime']

    #get table from rtime
    curs.execute('''SELECT rtime, corrective_insulin, bg, cgm, total_bolus_volume,ISF,ISF_rounded,ISF_trouble 
from insulin_carb_smoothed_2 
where rtime>= %s and rtime<= addtime(%s,'2:00')''',
                 [start,start])
    return curs.fetchall()

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

def get_isf_next(conn,rtime):
    '''returns the next ISF value after the given rtime; 
this lets us implement the 'next" button'''
    curs = conn.cursor(MySQLdb.cursors.DictCursor)
    curs.execute('''SELECT rtime from insulin_carb_smoothed_2 
                    where corrective_insulin = 1 and rtime > %s''',
                 [rtime])
    return curs.fetchone()['rtime']

def get_isf_details(conn,rtime):
    curs = conn.cursor(MySQLdb.cursors.DictCursor)
    curs.execute('''SELECT rtime,isf,bg0,bg1,bolus from isf_details where rtime = %s''',
                 [rtime])
    return curs.fetchone()

def get_all_isf_plus_buckets():
    conn = get_conn()
    curs = conn.cursor()
    curs.execute('''SELECT isf from isf_details;''')
    allData = curs.fetchall()
    curs.execute('''select time_bucket(rtime),isf from isf_details;''')
    bucketed = curs.fetchall()
    bucket_list = [ [ row[1] for row in bucketed if row[0] == b ]
                    for b in range(0,24,2) ]
    return(allData,bucket_list)

def get_isf_for_years(start_year,end_year):
    conn = get_conn()
    curs = conn.cursor()
    curs.execute('''SELECT isf from isf_details where year(rtime) >= %s and year(rtime)<= %s''',[start_year, end_year])
    allData = curs.fetchall()

    curs.execute('''SELECT time_bucket(rtime), isf from isf_details where year(rtime)>= %s and year(rtime) <= %s''',
                 [start_year, end_year])
    bucketed = curs.fetchall()
    bucket_list = [[ row[1] for row in bucketed if row[0] == b ]for b in range(0,24,2)]

    return (allData, bucket_list)
                   

def get_isf_for_bg (bg_value):
    conn = get_conn()
    curs = conn.cursor()

    curs.execute('''SELECT time_bucket(rtime), isf from isf_details where bg0 < %s ''', [bg_value])
    less_than = curs.fetchall()
    less_than_list = [ [ row[1] for row in less_than if row[0] == b] for b in range(0,24,2)]

    curs.execute('''SELECT time_bucket(rtime), isf from isf_details where bg0 > %s ''', [bg_value])
    greater_than = curs.fetchall()
    greater_than_list = [[row[1] for row in greater_than if row[0] == b] for b in range(0,24,2)]

    
    return (less_than_list, greater_than_list) 
    
def getRecentISF (time_bucket, num_weeks, min_data, debug=False):
    conn = get_conn ()
    curs = conn.cursor()

    def try_weeks(num_weeks):
        time_end = datetime.strptime("18/09/10", '%y/%m/%d') - timedelta(weeks = num_weeks)
        curs.execute ('''SELECT isf FROM isf_details where time_bucket(rtime) = %s and rtime > %s ''',
                      [time_bucket, time_end])

    def doubling_up(min_weeks):
        if debug:
            print('doubling up ',min_weeks)
        try_weeks(min_weeks)
        if curs.rowcount >= min_data:
            return recur(int(min_weeks/2), min_weeks)
        else:
            return doubling_up(min_weeks*2)

    def recur(min_weeks, max_weeks):
        mid = int((min_weeks+max_weeks)/2)
        if debug:
            print('recur ',min_weeks, mid, max_weeks)
        try_weeks(mid)
        if max_weeks == min_weeks + 1:
            # done, so either use min or max
            if (curs.rowcount < min_data):
                min_weeks = max_weeks
                try_weeks(min_weeks)
            # base case: 
            results = curs.fetchall()
            isf = [result[0] for result in results]
            isf = sorted(isf)
            return min_weeks, isf
        elif curs.rowcount >= min_data:
            # try lower half
            return recur(min_weeks,mid)
        else: 
            # try upper half
            return recur(mid,max_weeks)

    return doubling_up(num_weeks)

# hi there!

# new code to recompute ISF values from command line
if __name__ == '__main__':
    # compute_isf()
    print(getRecentISF(0,4,40,debug=True))
    print(getRecentISF(0,4,50,debug=True))
