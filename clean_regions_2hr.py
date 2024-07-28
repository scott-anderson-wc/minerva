
'''Iterate over 2hr clean regions to find clean regions used for: 
1. Clean ISFs and 
2. Reverse engineered IAC

Modified from isf2.py implemented by Scott 1/22/2019. 
Last updated by Mileva 7/28/24. 
"""

"""
Criteria for 2hr clean regions: 

1. There's a 30-minute window at the beginning of the 2-hour span for
ISF calculations. Any boluses in that 30 minute window are summed, and the 
last time is used for determining the beginning of the 2-hour span. 

2. There should be no bolus of any kind (corrective or not) within the
first 100" of the time interval (20 minutes from the end). This is
measured from the time of the last bolus in the beginning period.

3. The bolus should not be too small; it should be >= global variable min_bolus. 

4. If there is a bolus in the last 20 minutes, this allowed, but the
ISF value is stored in ISF_rounded instead of ISF.

'''

import MySQLdb
from datetime import timedelta
from dbi import get_conn # connect to the database
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

def get_longer_window(curs,start_time):
    curs.execute('''select rtime,corrective_insulin,bg,cgm,total_bolus_volume 
                    from insulin_carb_smoothed_2
                    where rtime >= %s and rtime <= addtime(%s,'5:00')''',
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
    # print('t2: {}, end_time: {}'.format(t2, end_time))
    for row in rows:
        # print (row['rtime'], row['total_bolus_volume'])

        # Final row
        if row['rtime'] == end_time:
            if bolus_count > 2:
                print('summed {} corrections!!'.format(bolus_count))
            return bolus_sum, t3

        ## Include try/ except for tbv of nonetype
        tbv = row['total_bolus_volume']             
        if tbv is not None and tbv > 0: 
            bolus_count += 1
            bolus_sum += tbv
            t3 = row['rtime']
    raise Exception('this should not happen')

def boluses_in_time_range(rows, start, end):
    for row in rows:
        time = row['rtime']
        tbv = row['total_bolus_volume']
        if start <= time <= end and tbv is not None and tbv > 0:
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

def get_clean_regions_2hr():
    conn = get_conn()
    curs = conn.cursor(MySQLdb.cursors.DictCursor)
    curs.execute('''select rtime, total_bolus_volume from insulin_carb_smoothed_2 
                    where corrective_insulin = 1''')
                    # and year(rtime) = 2018
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
    count = 0
    
    for row in rows:
        start = row
        t2 = start['rtime']
        t1 = t2 - timedelta(minutes=100)

        ## SKIPS regions if bolus appears in the 100 minute "before" window         
        if any_bolus_in_time_span(conn, t1,t2 - timedelta(minutes=5)):
            skipped_before += 1
            continue

        # get values for the next 2:30 (worst case scenario): 
        # rtime, corrective_insulin, bg, cgm, total_bolus_volume from t2 + 2.5 hrs
        rows = get_longer_window(curs, start['rtime'])

        # Sum the boluses in the first 30 minutes
        bolus_sum, t3 = bolus_sum_during_start(rows,t2)

        # SKIPS regions if bolus_sum too small 
        if bolus_sum < min_bolus:
            skipped_small += 1
            continue
        
        # from now on, use t3 rather than t2
        t4 = t3 + timedelta(minutes=100)
        t5 = t4 + timedelta(minutes=20)

        # SKIPS regions if boluses are present in 100 minute "middle" time (between t3 and t4) 
        if boluses_in_time_range(rows, t3+timedelta(minutes=5), t4-timedelta(minutes=5)):
            skipped_middle += 1
            continue
            
        ## Clean Regions
        # print(t3)
        bg_at_t3 = bg_at_time(rows, t3)
        bg_rows = get_bg_time_window(curs,t5)
        bg_at_t5 = bg_at_time_extended(bg_rows,t5)
        if bg_at_t3 and bg_at_t5:
            count += 1
            isf = (bg_at_t3 - bg_at_t5) / bolus_sum
            curs.execute('''replace into clean_regions_2hr_new (rtime,bg0,bg1,bolus,isf) values (%s,%s,%s,%s, %s)''',[t3,bg_at_t3,bg_at_t5, bolus_sum, isf]) 

    print(count)
    print('''There were {} corrective insulin events from 2014 -  present. 
{} events were skipped because of insulin before the START period
{} events were skipped because the bolus was too small
{} events were skipped because there was a bolus in the MIDDLE period
{} events were skipped because start BG was not available, 
{} events were skipped because end BG was not available, leaving
{} events with a good ISF and 
{} good events with insulin within 4 hours before event 
{} skipped + {} good is {} total.'''.format(total, skipped_before, skipped_small, skipped_middle, skipped_nobg_beg,skipped_nobg_end,good_isf,insulin_before,
                                            (skipped_before + skipped_small + skipped_middle + skipped_nobg_beg + skipped_nobg_end),
                                            good_isf,total))                    

# ================================================================

if __name__ == '__main__':
    get_clean_regions_2hr()
