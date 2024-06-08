'''Iterate over ICS2 and compute nudge_ISF values'''

'''
1. Compute nudge_isf_now = (cgm_now - cgm_next)/ DI_now 

2. Conditions: 
a) CGM and DI are not null
b) DI is nonzero
c) Time since last meal > 2 hours
d) No rescue carbs in the last hour
e) The DI must be > basal + min_DI, where min_DI = 0.35. 
f) Assumes a basal rate of 0.6 U/hr (this rate changed year to year though)
The above conditions may not perfectly align with those for clean_regions
See google docs (https://docs.google.com/document/d/17akLu24C9ik0tA6ojKXYRmnGofqcOZ2i3fuKvSHL3vM/edit) for futher specifics

3. Organizes ISF values into 24 buckets by time. Obtain the min, mean, std dev in 
each of these buckets

Implemented by Mileva 8/1/20
Updated 7/24/21
'''

import sys
import MySQLdb
import dbconn2
import csv
import math
import itertools
from datetime import datetime, timedelta,date
import dateparser
import decimal     # some MySQL types are returned as type decimal
from dbi import get_dsn, get_conn # connect to the database
import date_ui
import numpy as np
import json

def get_window_prior(curs, end_time):
    '''Gets the rows for the 1-hour window prior to the "end_time"'''
    curs.execute('''select rtime, rescue_carbs
                    from insulin_carb_smoothed_2
                    where rtime >= subtime(%s, "01:00:00") and rtime <= %s''',
                    [end_time, end_time])
    rows = curs.fetchall()
    return rows

def any_rescue_carbs(rows): 
    ''' Determines whether there were any rescue carbs given across the provided rows'''
    for _, rescue_carbs in rows: 
        if rescue_carbs: 
            return True
    
    return False    

def incomplete(row): 
    ''' Determines whether the row contains missing (none) values'''
    for i in range(len(row)): 
        if row[i] is None: 
            return True

    return False

# ==========================================================================================================================================
# 15-minute nudge isfs
# The following compute_nudge_isfs_15min function as written (does not subtract out the basal) provides the best nudge_isf values per bucket
# 
# Conditions (as specified at the top of the document): 
# a) CGM and DI are not null
# b) DI is nonzero
# c) Time since last meal > 2 hours
# d) No rescue carbs in the last hour
# e) The DI must be > basal + min_DI, where min_DI = 0.35. 
# f) Assumes a basal rate of 0.6 U/hr (this rate changed year to year though)
# The above conditions may not perfectly align with those for clean_regions
# See google docs (https://docs.google.com/document/d/17akLu24C9ik0tA6ojKXYRmnGofqcOZ2i3fuKvSHL3vM/edit) for futher specifics

def compute_nudge_isfs_15min(): 
    '''Computes the nudge_isf values for 15-minute increments using the following equation: 
        ISF = (cgm_now - AVERAGE cgm over the next 15 minute window) /  DI_now [- basal*]
        * currently does not subtract out basal, can modify to do so though'''

    ## Query
    conn = get_conn()
    curs = conn.cursor()
    curs.execute('''select rtime, cgm, dynamic_insulin, minutes_since_last_meal
                    from insulin_carb_smoothed_2''')
    rows = curs.fetchall()

    ## STATS
    total  = len(rows)
    skipped_meals = 0   # events skipped because meal within the past 2 hours
    skipped_rescue = 0  # events skipped because rescue carbs within 1 hour
    skipped_small = 0   # events skipped because DI < basal + minDI
    skipped_missing = 0 # events skipped because either cgm, di, or minutes_since_last_meal was missing
    skipped_zeroDI = 0  # events skipped because DI = 0

    ## SET UP: Constants and instantiation
    percentActiveInsulin = 1 / 33.713     # percent of insulin in effect in the first 5 minutes (based on normed IAC)
    steadyState = 1.693668513             # Based on a baseline basal of 0.6 units/ hr
    minDI = 0.35   

    ## SET UP: buckets by time of day (24 buckets)
    buckets = {}        
    for i in range(24):
        buckets[i] = []

    for row in rows:
        start_time, start_cgm, start_DI, minutes_since_last_meal = row

        curs.execute('''select avg(cgm)
                from insulin_carb_smoothed_2
                where rtime > subtime(%s, "0:15") and rtime <= %s''', [start_time, start_time])

        start_cgm_avg = curs.fetchone()[0]

        ## Row contains missing information
        if incomplete(row): 
            skipped_missing += 1
            continue

        # Get values for previous hour
        rows_previous_hour = get_window_prior(curs, start_time)

        ## Check for rescue carbs within past hour
        if any_rescue_carbs(rows_previous_hour):
            skipped_rescue += 1
            continue

        ## Check for meals within past 2 hours
        if minutes_since_last_meal <= 120: 
            skipped_meals += 1
            continue

        ## Excludes small DI values (below steady state + minDI)
        if start_DI < steadyState + minDI: 
            skipped_small += 1
            continue
        else: 
            di_without_basal = start_DI - steadyState 

        ## Obtain avg cgm across last 15 minutes
        curs.execute('''select avg(cgm)
                from insulin_carb_smoothed_2
                where rtime > %s and rtime <= addtime(%s, "0:15")''', [start_time, start_time])

        next_cgm_avg = curs.fetchone()[0]

        ## Compute ISF
        if next_cgm_avg is not None: 
            # Calculate ISF. The DI currently includes the basal
            # To exclude basal, replace "start_DI" with di_without_basal in the following equation
            isf = (float(start_cgm_avg) - float(next_cgm_avg))/ (start_DI * percentActiveInsulin)
            # Store ISF in buckets
            buckets[start_time.hour].append(isf)

    ## BUCKET ANALYSIS
    for hour in buckets: 
        isf_vals = buckets[hour] 

        zeroCount = 0 # Number of times isf = 0
        for isf_val in isf_vals:
            if isf_val == 0:
                zeroCount +=1
            
        count = len(isf_vals)
        mean = round(np.mean(isf_vals), 2)
        std_dev = round(np.std(isf_vals), 2)
        min_isfs = round(min(isf_vals), 2)
        max_isfs = round(max(isf_vals), 2)
        first_quartile = round(np.quantile(isf_vals, 0.25), 2)
        median = round(np.median(isf_vals), 2)
        third_quartile = round(np.quantile(isf_vals, 0.75), 2)
 
        print('Hour: {} \t count: {} \t mean: {:<8} \t median: {:<7} \t FirstQ: {:<7} \t ThirdQ: {:<7} \t min: {:<7} \t max: {:<5} \t stddev: {:<5}'.format(
            hour, count, mean, median, first_quartile, third_quartile, min_isfs, max_isfs, std_dev)) 

    return buckets
            
# ==========================================================================================================================================
# 5-minute nudge isfs ()
# The compute_nudge_isfs_5min function is not as good as the 15-minute nudge isf compuation. It has more outliers and values of large magnitudes
# Should be updated to exclude rescue carbs in the last hour in order to align with the computation for 15min nudge_isfs

def compute_nudge_isfs_5min(): 
    ''' Computes the nudge_isf values for 5-minute increments using the following equation: 
        ISF = (cgm_now - cgm_5_minutes before) /  DI_now [- basal*]
        * currently does not subtract out basal, can modify to do so though'''

    ## QUERY: get non-null rows. 
    conn = get_conn()
    curs = conn.cursor()
    curs.execute('''select rtime, cgm, dynamic_insulin
                from insulin_carb_smoothed_2
                where cgm IS NOT NULL and dynamic_insulin IS NOT NULL and minutes_since_last_meal > 120''')
    rows = curs.fetchall()
    print(len(rows))

    ## SET UP: Constants and instantiation
    timeInterval = 5                      # delta_t = 5 minues
    zeroDI = 0                            # keeps track of number of times there's a zero denominator
    percentActiveInsulin = 1 / 33.713     # percent of insulin in effect in the first 5 minutes (based on normed IAC)
    steadyState = 1.693668513             # Based on a baseline basal of 0.6 units/ hr
    minDI = 0.35                          # Arbitrary value

    ## SET UP: buckets by time of day (24 buckets)
    buckets = {}        
    for i in range(24):
        buckets[i] = []

    print("Criteria: minutes_since_last_meal > 120 and di_now > steadyState + minDI")

    ## COMPUTATION
    for i in range(len(rows) - 1):
        rtime_now, cgm_now, di_now = rows[i]
        rtime_next, cgm_next, di_next = rows[i + 1]
        time_diff = rtime_next - rtime_now

        if (time_diff.seconds == timeInterval * 60 and di_now > steadyState + minDI): 

            # # Substract out the basal insulin
            # di_without_basal = di_now - steadyState 

            # Calculate ISF
            isf = (cgm_now - cgm_next)/ (di_now * percentActiveInsulin)
            # Store ISF in buckets
            buckets[rtime_now.hour].append(isf)

    ## BUCKET ANALYSIS

    for hour in buckets: 
        isf_vals = buckets[hour] 

        zeroCount = 0 # Number of times isf = 0
        for isf_val in isf_vals:
            if isf_val == 0:
                zeroCount +=1
            
        count = len(isf_vals)
        mean = round(np.mean(isf_vals), 2)
        std_dev = round(np.std(isf_vals), 2)
        min_isfs = round(min(isf_vals), 2)
        max_isfs = round(max(isf_vals), 2)
        first_quartile = round(np.quantile(isf_vals, 0.25), 2)
        median = round(np.median(isf_vals), 2)
        third_quartile = round(np.quantile(isf_vals, 0.75), 2)
 
        print('Hour: {} \t count: {} \t mean: {:<8} \t median: {:<7} \t FirstQ: {:<7} \t ThirdQ: {:<7} \t min: {:<7} \t max: {:<5} \t stddev: {:<5}'.format(
            hour, count, mean, median, first_quartile, third_quartile, min_isfs, max_isfs, std_dev)) 

    return buckets

    # with open ("nudge_isf_buckets_without_basal.json", "w") as outFile: 
    #     json.dump(buckets, outFile) 

def find_isf_example(time_bucket, query_isf):
    '''Takes an int between 0-23 (hour) and a value (ISF). Identifies the example within the given time_bucket 
    with the closest ISF value and returns the surrounding 40 rows (samples). Uses 5-min nudge isfs and applies the same conditions as 
    used in compute_nudge_isfs_5min'''
    
    ## QUERY: get non-null rows
    conn = get_conn()
    curs = conn.cursor()
    curs.execute('''select rtime, cgm, dynamic_insulin
                from insulin_carb_smoothed_2
                where cgm IS NOT NULL and dynamic_insulin IS NOT NULL and minutes_since_last_meal > 120''')
    rows = curs.fetchall()

    ## SET UP: Constants
    timeInterval = 5    # delta_t = 5 minues
    percentActiveInsulin = 1 / 33.713     # percent of insulin in effect in the first 5 minutes (based on normed IAC)
    steadyState = 1.693668513
    minDI = 0.35        

    ## SET UP: Instantiate Counters
    zeroDI = 0              # keeps track of number of times there's a zero denominator
    nearest_isf_index = -1  # keeps track of index with nearest ISF
    nearest_isf_diff = 100000    # keeps track of the difference in magnitude of the closest ISF
    nearest_isf = 100000

    print("Criteria: minutes_since_last_meal > 120 and di_now > steadyState + minDI")

    ## COMPUTATION
    for i in range(len(rows) - 1):
        rtime_now, cgm_now, di_now = rows[i]
        rtime_next, cgm_next, di_next = rows[i + 1]
        time_diff = rtime_next - rtime_now

        ## Compute ISF 
        if (time_diff.seconds == timeInterval * 60 and di_now > steadyState + minDI): 
            # di_without_basal = di_now - steadyState     # Substract out the basal insulin
            current_isf = (cgm_now - cgm_next)/ (di_now * percentActiveInsulin)   # Calculate ISF

            ## Updates if the computed ISF is close to the query_isf 
            isf_diff = abs(current_isf - query_isf)
            if (rtime_now.hour == time_bucket) and (isf_diff < nearest_isf_diff):
                nearest_isf_diff = isf_diff
                nearest_isf_index = i
                nearest_isf = current_isf

    print("Query: Bucket {}, Desired ISF {}".format(time_bucket, query_isf))
    print("Index of nearest ISF: {}, ISF value: {}, Difference in ISF values: {}".format(nearest_isf_index, round(nearest_isf, 4),round(nearest_isf_diff, 4)))

    ## Display: Prints values for 40 surrounding rows
    for i in range(nearest_isf_index - 20, nearest_isf_index + 20 - 1):
        rtime_now, cgm_now, di_now = rows[i]
        rtime_next, cgm_next, di_next = rows[i + 1]
        time_diff = rtime_next - rtime_now

        ## Obtain ISF value of surrounding rows
        if (time_diff.seconds == timeInterval * 60 and di_now > steadyState + minDI): 
            di_without_basal = di_now - steadyState     # Substract out the basal insulin
            isf = (cgm_now - cgm_next)/ (di_without_basal * percentActiveInsulin)   # Calculate ISF
        
        ## Print ISF values of 40 surrounding rows
        if (i == nearest_isf_index): 
            print("*** {}: {}, cgm {}, di {}, isf {} ***".format(i, rtime_now, cgm_now, di_now, isf))
        else: 
            print("{}: {}, cgm {}, di {}, isf {}".format(i, rtime_now, cgm_now, di_now, isf))


# ================================================================

if __name__ == '__main__':
    conn = get_conn()
    compute_nudge_isfs_5min()
    # find_isf_example(23, -57.89)
    # curs = conn.cursor()
    # rows = get_window_prior(curs, '2018-01-01 20:50:00')
    # any_rescue_carbs(rows)
    # print("Beginning 15 min nudge ISF computations (~2min)")
    # compute_nudge_isfs_15min()
