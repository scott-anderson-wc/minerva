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

Revised 1/25/2021 to use cs304dbi

'''

import sys
import cs304dbi as dbi
import csv
import math
import itertools
from datetime import datetime, timedelta,date
import decimal                  # some MySQL types are returned as type decimal
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
    curs = dbi.cursor(conn)
    curs.execute('''select count(*) from insulin_carb_smoothed_2 
                    where total_bolus_volume > 0
                    and %s <= rtime and rtime <= %s''',
                 [date_ui.python_datetime_to_mysql_datetime(start),
                  date_ui.python_datetime_to_mysql_datetime(end)])
    result = curs.fetchone()
    return result[0] > 0


def zero_if_none(val):
    return 0 if val is None else val

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
                print(('summed {} corrections!!'.format(bolus_count)))
            return bolus_sum, t3
        tbv = zero_if_none(row['total_bolus_volume'])
        if tbv > 0: 
            bolus_count += 1
            bolus_sum += tbv
            t3 = row['rtime']
    raise Exception('this should not happen')

def boluses_in_time_range(rows, start, end):
    for row in rows:
        time = row['rtime']
        if start <= time <= end and zero_if_none(row['total_bolus_volume']) > 0:
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
        if base_index + delta >= len(rows):
            return None
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

def compute_isf(debug=False):
    '''compute ISF values for all clean corrections in the database;
store results in isf_details table. This should be run whenever
there's new data.

    Eventually, need to come up with an incremental version. For now
(as of July 2024), this code processes 10,671 corrective insulin
events into 2699 good events in about 30 seconds, which is good
enough.

    '''
    conn = dbi.connect()
    print('conn autocommit: {}'.format(conn.autocommit_mode))
    # July 2024, I'm not sure why we need autocommit. Maybe just
    # commit at the end? Or after doing the DDL?
    conn.autocommit(True)
    print('conn autocommit: {}'.format(conn.autocommit_mode))
    curs = dbi.dict_cursor(conn)
    curs.execute('update insulin_carb_smoothed_2 SET ISF_trouble = null, isf = null, ISF_rounded = null')
    curs.execute('delete from isfvals') # make sure table is initially empty
    curs.execute('delete from isf_details') # make sure table is initially empty
    # just for reporting
    curs.execute('''select min(rtime), max(rtime), count(rtime) 
                    from insulin_carb_smoothed_2
                    where corrective_insulin = 1 ''')
    stats_dict = curs.fetchone()
    print('There are {} correction events from {} to {}'.format(
        stats_dict['count(rtime)'],
        stats_dict['min(rtime)'],
        stats_dict['max(rtime)']))
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
        if debug: print('\ncorrective insulin at {}'.format(t2))

        prior_insulin = any_bolus_in_time_span(conn, t2 - timedelta(hours=4),t1)

        if any_bolus_in_time_span(conn, t1,t2 - timedelta(minutes=5)):
            if debug: print('skipping {} because of insulin in the BEFORE period: {} to {}'.format(t2,t1,t2))
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
            if debug: print('bolus sum {} is too small; skipping {}'.format(bolus_sum,t3))
            curs.execute('''UPDATE insulin_carb_smoothed_2 SET ISF_trouble = %s where rtime = %s''',
                         ['bolus too small', t3])
            skipped_small += 1
            continue
        
        # from now on, use t3 rather than t2, particularly for looking up BG
            
        t4 = t3 + timedelta(minutes=100)
        t5 = t4 + timedelta(minutes=20)

        # Check for no boluses in middle time
        if boluses_in_time_range(rows, t3+timedelta(minutes=5), t4-timedelta(minutes=5)):
            if debug: print('skipping {} because of insulin in the middle period'.format(t3))
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
            if debug: print('insulin in the end period: {} to {}'.format(t4,t5))
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
                if debug: print('at {} BAD ISF {}'.format(t3, isf))
                curs.execute('''UPDATE insulin_carb_smoothed_2 SET ISF_trouble = %s, ISF_rounded = %s where rtime = %s''',
                             ['insulin at end', isf, t3])
            else: 
                if debug: print('at {} GOOD ISF {}'.format(t3, isf))
                curs.execute('''UPDATE insulin_carb_smoothed_2 SET isf = %s where rtime = %s''', [isf, t3])
            # New: record details of the calc in the isfvals table. [Scott 12/13/2019]
            #curs.execute('''insert into isf_details(rtime,isf,bg0,bg1,bolus) values (%s,%s,%s,%s,%s)''',
                        # [t3, isf, bg_at_t3, bg_at_t5, bolus_sum])
            if debug: print('ISF_DETAILS at {} caculated {}'.format(t3, isf))
            curs.execute('''insert into isf_details(rtime,isf,bg0,bg1,bolus,prior_insulin) values (%s,%s,%s,%s,%s,%s)''',
                         [t3,isf,bg_at_t3,bg_at_t5, bolus_sum,prior_insulin])
        else:
            #skipped_bg += 1
            skipped = False  
            if not bg_at_t3:
                skipped_nobg_beg += 1
                skipped = True
                if debug: print('at {} BAD ISF {}'.format(t3, 'nobg'))
                curs.execute('''UPDATE insulin_carb_smoothed_2 set ISF_trouble = %s where rtime = %s''',
                             [ 'nobg', t3]) # 'missing start BG value'
            if not bg_at_t5 and not skipped:
                skipped_nobg_end += 1
                #print 'nobg at end', t3
                if debug: print('at {} BAD ISF {}'.format(t3, 'nobg'))
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
    print(('''There were {} corrective insulin events:
{} events were skipped because of insulin before the START period
{} events were skipped because the bolus was too small
{} events were skipped because there was a bolus in the MIDDLE period
{} events were skipped because start BG was not available, 
{} events were skipped because end BG was not available, leaving
{} events with a good ISF and 
{} good events with insulin within 4 hours before event 
{} skipped + {} good is {} total.'''.format(total, skipped_before, skipped_small, skipped_middle, skipped_nobg_beg,skipped_nobg_end,good_isf,insulin_before,
                                            (skipped_before + skipped_small + skipped_middle + skipped_nobg_beg + skipped_nobg_end),
                                            good_isf,total)))
                                            

def get_first_corrective_insulin(year=2018):
    conn = dbi.connect()
    curs = dbi.dict_cursor(conn)
    curs.execute('''SELECT min(rtime) as rtime from insulin_carb_smoothed_2 
where corrective_insulin = 1 and year(rtime) = %s''',
                 [year])
    start = curs.fetchone()['rtime']
    return start

## currently, this function is only used to display ISF values, not for computing anything.

def get_isf(rtime):
    '''get two-hour set of rows from ICS2 with corrective_insulin, bg, cgm, total_bolus_volume, ISF, ISF_rounded, and ISF_trouble'''
    conn = dbi.connect()
    curs = dbi.dict_cursor(conn)
    rows = curs.execute('''SELECT rtime from insulin_carb_smoothed_2  where corrective_insulin = 1 and rtime > %s''',[rtime])
    if rows == 0:
        raise Exception('no corrective insulin after given rtime: {}'.format(rtime))
    start = curs.fetchone()['rtime']

    #get table from rtime
    curs.execute('''SELECT rtime, corrective_insulin, bg, cgm, total_bolus_volume,ISF,ISF_rounded,ISF_trouble 
from insulin_carb_smoothed_2 
where rtime>= %s and rtime<= addtime(%s,'2:00')''',
                 [start,start])
    return curs.fetchall()

## this is also used just for display.

def get_isf_at(conn,rtime):
    '''Return the first actual ISF value at or after the given time'''
    curs = dbi.dict_cursor(conn)
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
    curs = dbi.dict_cursor(conn)
    curs.execute('''SELECT rtime from insulin_carb_smoothed_2 
                    where corrective_insulin = 1 and rtime > %s''',
                 [rtime])
    return curs.fetchone()['rtime']

def get_isf_details(conn,rtime):
    curs = dbi.dict_cursor(conn)
    curs.execute('''SELECT rtime,isf,bg0,bg1,bolus from isf_details where rtime = %s''',
                 [rtime])
    return curs.fetchone()

def get_all_isf_plus_buckets():
    ''' Returns all good isf values and all isf values in 2-hour time buckets'''
    conn = dbi.connect()
    curs = dbi.dict_cursor(conn)
    curs.execute('''SELECT isf from isf_details;''')
    allData = curs.fetchall()
    curs.execute('''select time_bucket(rtime),isf from isf_details;''')
    bucketed = curs.fetchall()
    bucket_list = [ [ row[1] for row in bucketed if row[0] == b ]
                    for b in range(0,24,2) ]
    return(allData,bucket_list)

def get_isf_for_years(start_year,end_year):
    '''returns all isf values and all isf values in 2-hour time buckets for a specific time period (in years) '''
    print('obsolete function; prefer get_isf_between')
    conn = dbi.connect()
    curs = dbi.dict_cursor(conn)
    curs.execute('''SELECT isf from isf_details where year(rtime) >= %s and year(rtime)<= %s''',[start_year, end_year])
    allData = curs.fetchall()

    curs.execute('''SELECT time_bucket(rtime), isf from isf_details where year(rtime)>= %s and year(rtime) <= %s''',
                 [start_year, end_year])
    bucketed = curs.fetchall()
    bucket_list = [[ row[1] for row in bucketed if row[0] == b ]for b in range(0,24,2)]

    return (allData, bucket_list)
                   
def get_isf_between(conn, start_time, end_time=datetime.now()):
    '''returns all isf values and all isf values in 2-hour time
    buckets for a specific time period. Returned as a list of tuples:
    (bucket, isf). Represented as tuples for conciseness.
    '''
    curs = dbi.cursor(conn)
    curs.execute('''SELECT time_bucket(rtime), isf from isf_details where rtime between %s and %s''',
                 [start_time, end_time])
    return curs.fetchall()

def get_isf_for_bg (bg_value):
    ''' returns isf values and isf values in 2-hour time buckets for a specific starting bg value'''
    conn = dbi.connect()
    curs = dbi.cursor(conn)
    curs.execute('''SELECT time_bucket(rtime), isf from isf_details where bg0 < %s ''', [bg_value])
    less_than = curs.fetchall()
    less_than_list = [ [ row[1] for row in less_than if row[0] == b] for b in range(0,24,2)]

    curs.execute('''SELECT time_bucket(rtime), isf from isf_details where bg0 > %s ''', [bg_value])
    greater_than = curs.fetchall()
    greater_than_list = [[row[1] for row in greater_than if row[0] == b] for b in range(0,24,2)]

    
    return (less_than_list, greater_than_list) 
    
def get_recent_ISF (time_bucket, num_weeks, min_data, debug=False):
    '''returns at least min_data isf values for a specific 2-hour time
    bucket looking back num_weeks (or more depending on available data
    points)'''
    conn = dbi.connect()
    curs = dbi.cursor(conn)

    def try_weeks(num_weeks):
        # time_end = datetime.strptime("18/09/10", '%y/%m/%d') - timedelta(weeks = num_weeks)
        ISF_TABLE = 'clean_regions_2hr_new' # isf_details
        nrows = curs.execute (f'''SELECT isf FROM {ISF_TABLE}
                                  WHERE time_bucket(rtime) = %s
                                  AND rtime > date_sub(current_date(), interval %s week)''',
                      [time_bucket, num_weeks])
        if debug:
            print(f'There have been {nrows} ISF values in the last {num_weeks} weeks')

    def doubling_up(min_weeks):
        if debug:
            print(('doubling up ',min_weeks))
        try_weeks(min_weeks)
        if curs.rowcount >= min_data:
            return recur(int(min_weeks/2), min_weeks)
        else:
            return doubling_up(min_weeks*2)

    def recur(min_weeks, max_weeks):
        mid = int((min_weeks+max_weeks)/2)
        if debug:
            print(('recur ',min_weeks, mid, max_weeks))
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

# ================================================================
# get an ISF estimate for a point in time based on data prior to that time.


# from https://stackoverflow.com/questions/24101524/finding-median-of-list-in-python

def median(lst):
    '''return median of list; list is modified'''
    quotient, remainder = divmod(len(lst), 2)
    lst.sort()
    if remainder:
        return lst[quotient]
    return sum(lst[quotient - 1:quotient + 1]) / 2.

def to_list(tuple_seq):
    '''MySQL gives us a tuple of tuples, but we need a list of numbers'''
    return [ x[0] for x in tuple_seq ]

min_rtime_cache = None

def min_rtime():
    global min_rtime_cache
    if min_rtime_cache is None:
        conn = dbi.connect()
        curs = dbi.cursor(conn)
        curs.execute('''select min(rtime) from insulin_carb_smoothed_2''')
        min_rtime_cache = curs.fetchone()[0]
    return min_rtime_cache
    
## This function is badly named. Must've been just for debugging

def max_rtime():
    conn = dbi.connect()
    curs = dbi.cursor(conn)
    curs.execute('''select max(rtime) from isf_details''')
    return curs.fetchone()[0]

def datetime_bucket(dt):
    '''returns the bucket: 0-22'''
    return dt.hour//2*2

def datetime_quarter(dt):
    '''returns the quarter: 1-4'''
    return 1+(dt.month-1)//3

def datetime2quarter_start(dt):
    '''Returns the first date in the quarter, and the first hour in the time bucket.'''
    return datetime(dt.year,
                    (dt.month-1)//3*3+1,
                    1,
                    datetime_bucket(dt),
                    0)

def test_datetime2quarter_start():
    aug1=datetime(2018,8,1,11,0)
    for delta_day in range(15):
        for delta_time in range(40):
            x = aug1+timedelta(days=delta_day,minutes=delta_time*10)
            y = datetime2quarter_start(x)
            print(('{} => {}'.format(x,y)))

def delta_quarter(dt,dq):
    '''Returns a datetime in the preceding or following quarters,
where dq is the delta in quarters. Assumes 12 weeks earlier will 
get the prior quarters, and 14 weeks later will get the following ones.'''
    delta_weeks = dq * 12 if dq < 0 else dq * 14
    alt = dt + timedelta(weeks=delta_weeks)
    return datetime2quarter_start(alt)

def test_delta_quarter():
    dt = date_ui.to_datetime('7/1/2016 14:00')
    for dq in range(-4,3):
        print((dt,dq,delta_quarter(dt,dq)))

# ================================================================

# cache for real ISF values, indexed by (bucket, year, quarter)
isf_cache = {'hits':0,'misses':0}

ignore_isf_cache = False

def isf_values(curs, bucket, rtime):
    '''This cached lookup gets the ISF values for the quarter that the
rtime is in, which might include future values. The values are drawn
from the isf_details table, which is filled by

    '''
    year = rtime.year
    quarter = datetime_quarter(rtime)
    key = (bucket, year, quarter)
    if (ignore_isf_cache or key not in isf_cache):
        isf_cache['misses'] += 1
        curs.execute('''select isf from isf_details 
                        where time_bucket(rtime) = %s
                        and year(rtime)=%s and quarter(rtime)=%s''',
                     key)
        vals = [ tup[0] for tup in curs.fetchall() ]
        isf_cache[key] = vals
    else:
        isf_cache['hits'] += 1
    return isf_cache[key]

def test_isf_values(dt=date_ui.to_datetime('3/14/2015 01:15')):
    '''gets ISF values twice; the second should be cached. The first rtime
is the argument and the second is the next quarter (92 days later).
    '''
    conn = dbi.connect()
    curs = dbi.cursor(conn)
    dt0 = min_rtime()
    print((isf_values(curs, 18, dt0)))
    print((isf_values(curs, 18, dt0)))
    print((isf_values(curs, 18, dt0 + timedelta(days=3*92))))
    print((isf_values(curs, 18, dt0 + timedelta(days=3*92))))
    print(isf_cache)

# cache for estimated ISF values, indexed by (bucket, year, quarter)
isf_est_cache = {}

def compute_estimated_isf_at_time(dt,
                                  min_data=20, # 25 doesn't work for dt=3/15/2014 06:00
                                  debug=False,
                                  verbose=False):
    '''Return an estimated ISF value to use for the given datetime (dt), 
and seeking at least min_data. Any date in the same quarter will yield the same value.
We may use values from neighboring quarters and buckets.'''
    dt = dt if type(dt) == datetime else date_ui.to_datetime(dt)
    year, quarter = dt.year, datetime_quarter(dt)
    bucket = datetime_bucket(dt)
    if verbose: print('key is year {}, quarter {} bucket {}'.format(year,quarter,bucket))
    key = (bucket, year, quarter)
    if debug and key in isf_est_cache:
        del isf_est_cache[key]
    if key not in isf_est_cache:
        if verbose: print('key not in cache; recomputing')
        # date at the beginning of the quarter
        dtq_curr = datetime2quarter_start(dt)
        conn = dbi.connect()
        curs = dbi.cursor(conn)
        prev_bucket = (bucket - 2) % 24
        next_bucket = (bucket + 2) % 24
        # the 'option' value is just a convenient label for the place(s) we are searching
        # A is curr quarter, B before that, C before B and D includes the next quarter
        # the 2 version looks in the two neighboring buckets
        for q0,q1,neighbors,option in [(0,0,False,'A'),
                                       (0,0,True,'A2'),
                                       (-1,0,False,'B'),
                                       (-1,0,True,'B2'),
                                       (-2,0,False,'C'),
                                       (-2,0,True,'C2'),
                                       # look forward
                                       (-2,1,False,'D'),
                                       (-2,1,True,'D2')]:
            if debug:
                print(('option {}: searching quarters from {} to {} {} neighbor buckets'
                       .format(option,q0,q1,'with' if neighbors else 'without')))
            all_vals = []
            for q in range(q0,q1+1):
                dtq_other = delta_quarter(dtq_curr,q)
                vals = isf_values(curs,bucket,dtq_other)
                all_vals += vals
                if debug:
                    print(('got {} values'.format(len(vals))))
                if verbose: print('got {} values from bucket {} and quarter {}: {}'.format(len(vals),bucket,dtq_other,vals))
                if neighbors:
                    vals = isf_values(curs,prev_bucket,dtq_other)
                    if verbose: print('got {} values from prev bucket {} and quarter {}: {}'.format(len(vals),prev_bucket,dtq_other,vals))
                    all_vals += vals
                    if debug:
                        print(('with prev neighbor buckets {} got {} values'.format(prev_bucket,len(vals))))
                    vals = isf_values(curs,next_bucket,dtq_other)
                    if verbose: print('got {} values from next bucket {} and quarter {}: {}'.format(len(vals),next_bucket,dtq_other,vals))
                    all_vals += vals
                    if debug:
                        print(('with next neighbor buckets {} got {} values'.format(next_bucket,len(vals))))
            # is it enough?
            if verbose: print('in total, got {} vals: {}'.format(len(all_vals),all_vals))
            if len(all_vals) >= min_data:
                isf_est_cache[key] = round(median(all_vals),2), option, len(all_vals)
                if debug:
                    print(('done option {} with {} values'.format(option,len(all_vals))))
                break
            else:
                if debug:
                    print('not yet enough values: {} < {}; keep trying'.format(len(all_vals),min_data))
        if key not in isf_est_cache:
            # if we get to here, every option failed. Just return the last
            isf_est_cache[key] = round(median(vals),2), 'FAIL', len(vals)
    # after the skippable computation, just use cached value
    return isf_est_cache[key]

class stats:
    def __init__(self):
        # let's start with the trivial implementation that keeps all values
        self.vals = []
        self.count = 0
        self.sum = 0
        self.sum_squares = 0
        self.min = None
        self.max = None

    def update(self,val):
        self.vals.append(val)
        self.count += 1
        self.sum += val
        self.sum_squares += val*val
        if self.min is None or val < self.min:
            self.min = val
        if self.max is None or val > self.max:
            self.max = val

    def report(self):
        # see https://www.thoughtco.com/sum-of-squares-formula-shortcut-3126266
        if self.min == self.max:
            # if all values are the same, numerical roundoff in shortcut can yield negative SSD
            std_dev = 0.0
        else:
            sum_squared_deviations = self.sum_squares - self.sum*self.sum/self.count
            std_dev = math.sqrt(sum_squared_deviations/self.count)
        return {'count': self.count,
                'mean': self.sum/self.count,
                'min': self.min,
                'max': self.max,
                'stddev': std_dev,
                'median': median(self.vals)}


def test_stats():
    s = stats()
    for x in range(10):
        s.update(x)
    print((s.report()))


def test_isf_at_time(min_dt=None, max_dt=None):
    '''This tests the computation of estimated ISF values (the function
earlier). It goes through every year, quarter and bucket, invokes
isf_at_time, collects the return values and updates the statistics.

    '''
    if min_dt is None:
        min_dt = min_rtime()
    if max_dt is None:
        max_dt = max_rtime()
    all_count = 0
    counts = {}
    isfs = []
    conn = dbi.connect()
    curs = dbi.cursor(conn)
    print(('iterating from {} to {}'.format(min_dt,max_dt)))
    dt = min_dt
    curr_quarter = datetime_quarter(dt)
    print(('starting at',datetime.now().strftime('%H:%M:%S')))
    st = [ stats() for b in range(0,24) ]
    while dt < max_dt:
        if datetime_quarter(dt) != curr_quarter:
            curr_quarter = datetime_quarter(dt)
            print(('at',datetime.now().strftime('%H:%M:%S')))
            print(('Now in {}/{}'.format(dt.year,curr_quarter)))
            print(('option counts',counts))
            print(('isf cache',len(isf_cache),isf_cache['hits'],isf_cache['misses']))
            
            for bucket in range(0,24,2):
                if st[bucket].min < st[bucket].max:
                    print(('stats for {}'.format(bucket),st[bucket].report()))
            global gst
            gst = st
            # reset the stats
            st = [ stats() for b in range(0,24) ]
        # normal processing
        isf,opt,n = compute_estimated_isf_at_time(dt, debug=False)
        isfs.append(isf)
        (st[ 2*math.floor(dt.hour/2.0) ]).update(isf)
        # print((dt,isf,opt))
        counts[opt] = 1 + counts.get(opt,0)
        all_count += 1
        dt = dt + timedelta(minutes=5)
    print(('Estimated ISF {} times'.format(all_count)))
    print('results were like this: ')
    print(counts)
    global gisfs
    gisfs = isfs
    print((min(isfs), max(isfs)))

# ================================================================
# some of the interpolated ISF values computed by the function above
# are weird:  54.51084999999935 and many others with many decimal
# places. That's odd. I'm going to find out how long they are:

def long_isf_values():
    longest = 1
    conn = dbi.connect()
    curs = dbi.cursor(conn)
    curs.execute('''select isf from isf_details''')
    for row in curs.fetchall():
        isf = row[0]
        if len(str(isf)) > longest:
            longest = len(str(isf))
            print(('next longest:',isf))


# ================================================================

def isf_density():
    conn = dbi.connect()
    curs = dbi.cursor(conn)
    # this could be way more efficient
    for year in range(2014,2019):
        # for month in range(1,13):
        for quarter in range(1,5):
            # vals = [str(year),str(month)]
            vals = [str(year),str(quarter)]
            for bucket in range(0,24,2):
                dt = datetime(year,(quarter-1)*3+1,1,bucket,0)
                curs.execute('''select count(*) from isf_details
                                where year(rtime)=%s and quarter(rtime)=%s
                                and time_bucket(rtime)=%s''',
                             [year,quarter,bucket])
                count = curs.fetchone()[0]
                vals.append(str(count))
            print(('\t'.join(vals)))

def est_isf_values():
    conn = dbi.connect()
    curs = dbi.cursor(conn)
    headers = ['YYYY','Q']
    headers.extend([str(b) for b in range(0,24,2)])
    print(('\t'.join(headers)))
    # this could be way more efficient
    for year in range(2014,2019):
        # for month in range(1,13):
        for quarter in range(1,5):
            # vals = [str(year),str(month)]
            vals = [str(year),str(quarter)]
            for bucket in range(0,24,2):
                dt = datetime(year,(quarter-1)*3+1,1,bucket,0)
                isf,opt,n = compute_estimated_isf_at_time(dt)
                vals.append(str(n))
            print(('\t'.join(vals)))

# ================================================================

def tsv_out(*args):
    print(('\t'.join(map(str,args))))

def est_isf_table():
    '''Write out the EST_ISF values in TSV format 
for reading into a MySQL table to pre-compute them
This prints to stdout, so you can pipe the result
into a file of your choosing.
Columns are year,quarter,bucket,isf,option,n
where option are how the data was computed and 
n is the number of real values that the median is
computed from.'''
    conn = dbi.connect()
    curs = dbi.cursor(conn)
    for year in range(2014,2022):
        # for month in range(1,13):
        for quarter in range(1,5):
            # vals = [str(year),str(month)]
            vals = [str(year),str(quarter)]
            for bucket in range(0,24,2):
                dt = datetime(year,(quarter-1)*3+1,1,bucket,0)
                isf,opt,n = compute_estimated_isf_at_time(dt)
                tsv_out(year,quarter,bucket,isf,opt,n)
                
# ================================================================

def regression_data():
    '''Regression data will start with Q2 of 2014 and go to Q4 of 2018, 
the last quarter for which we have good data'''
    conn = dbi.connect()
    curs = dbi.cursor(conn)
    est_isf = {}
    curs.execute('select year,quarter,time_bucket,isf_est from isf_est')
    for row in curs.fetchall():
        (y,q,t,i) = row
        if '2014-1' < y+'-'+q <= '2018-4':
            est_isf[(y,q,t)] = i
    # print('isf_est.keys()')
    for row in sorted(est_isf.keys()):
        # print(row)
        pass
    # print('iterate over insulin_carb_smoothed_2')
    # we need 3 good rows in a row: the difference between
    # the first two gives us the bg_slope, and we try to
    # predict the third. 
    prev_prev_bg = None
    prev_bg = None
    prev_di = None
    curs.execute('''
select rtime,cgm,bg,dynamic_insulin 
from insulin_carb_smoothed_2
where rtime >= '2014-04-01' 
  and rtime < '2019-01-01';
''')
    tsv_out('good_bg','prev_bg','bg_slope','isf','di','di_slope')
    linear, nonlinear = 0,0
    for row in curs.fetchall():
        (rtime,cgm,bg,di) = row
        if di is None or (cgm is None and bg is None):
            prev_prev_bg = None
            continue
        good_bg = bg if bg is not None else cgm
        if prev_prev_bg is None:
            prev_prev_bg = good_bg
            continue
        index = str(rtime.year), str((rtime.month-1)//3+1), str((rtime.hour//2)*2)
        isf = est_isf[index]    # could avoid this lookup, but not going to bother
        if prev_bg is None:
            prev_bg,prev_di = (good_bg,di)
            continue
        bg_slope = prev_bg - prev_prev_bg
        di_slope = prev_di - di
        # sanity test
        if bg == (prev_bg + bg_slope):
            linear += 1
        else:
            nonlinear += 1
        tsv_out(good_bg,prev_bg,bg_slope,isf,di,di_slope)
        # shift current values to prev values
        prev_prev_bg,prev_bg,prev_di = (prev_bg,good_bg, di)
    # afterwards, print how many linear and nonlinear steps we had
    msg = 'linear: {} nonlinear: {}'.format(linear,nonlinear)
    # The 2to3 refactoring tool can't handle the following
    print(msg, file=sys.stderr)

# ================================================================
# The regression table computed by the previous code, pulling out
# just 20K rows near the end, gave us the following regression
# model (dropping the ISF value, which was not significant)
# and rounding numbers to a reasonable number of digits (3).

# predicted_bg = 2.7 + 0.985 * prev_bg - 0.228 * bg_slope - 0.175 * di - 1.3 * di_slope

MODEL = {'constant': 2.7, 'prev_bg': 0.985, 'bg_slope': 0.288, 'di': 0.175, 'di_slope': 1.3}

# the following code implements that model, filling in those values into the
# Predicted_BG column that Anah added to insulin_carb_smoothed_2.

def compute_predicted_bg():
    '''implements the regression model and updates the insulin_carb_smoothed_2 table 
with the predictions. These are just one-step predictions, not 2 hour extrapolations.'''
    conn = dbi.connect()
    curs = dbi.cursor(conn)
    update = conn.cursor()
    # we need 3 good rows in a row: the difference between
    # the first two gives us the bg_slope, and we predict 
    # the third. 
    prev_prev_bg = None
    prev_bg = None
    prev_di = None
    curs.execute('''
select rtime,cgm,bg,dynamic_insulin 
from insulin_carb_smoothed_2
where rtime >= '2014-04-01' 
  and rtime < '2019-01-01';
''')
    for row in curs.fetchall():
        (rtime,cgm,bg,di) = row
        if di is None or (cgm is None and bg is None):
            prev_prev_bg = None
            continue
        good_bg = bg if bg is not None else cgm
        if prev_prev_bg is None:
            prev_prev_bg = good_bg
            continue
        if prev_bg is None:
            prev_bg,prev_di = (good_bg,di)
            continue
        bg_slope = prev_bg - prev_prev_bg
        di_slope = prev_di - di
        # compute regression model
        predicted_bg = (MODEL['constant'] +
                        MODEL['prev_bg'] * prev_bg +
                        MODEL['bg_slope'] * bg_slope +
                        MODEL['di'] * di + 
                        MODEL['di_slope'] * di_slope)
        update.execute('''
            update insulin_carb_smoothed_2
            set predicted_bg = %s
            where rtime = %s''',
                       [predicted_bg,rtime])
        # shift current values to prev values
        prev_prev_bg,prev_bg,prev_di = (prev_bg,good_bg, di)


# ================================================================

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        expr = sys.argv[1]
        if expr == 'compute_isf':
            compute_isf()
        else:
            print('evaluating {}'.format(expr), file=sys.stderr)
            eval(expr)
    else:
        # if there's no command line arg, do this:
        compute_predicted_bg()
        
    # compute_isf()
    # import pdb; pdb.set_trace()
    # long_isf_values()
    # test_isf_at_time(min_rtime(),date_ui.to_datetime('12/1/2014 1:00am'))
    # isf_density()
    # est_isf_values()
    # test_isf_at_time()
    # est_isf_values()
    # est_isf_table()
    # regression_data()
