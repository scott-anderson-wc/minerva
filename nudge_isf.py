'''Iterate over ICS2 and compute ISF values

Author: Mileva
Last Updated: 6/7/24
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
    
def any_rescue_carbs_dict(rows): 
    ''' Determines whether there were any rescue carbs given across the provided rows'''
    for row in rows: 
        if row["rescue_carbs"]: 
            return True
    
    return False    
    
def incomplete(row): 
    ''' Determines whether the row contains missing (none) values'''
    if hasattr(row, "values"): 
        # if dict, look at only dict values
        row = row.values()
    for val in row: 
        if val is None: 
            return True

    return False
    
# ==========================================================================================================================================
# Nudge ISFs computed from clean regions

def clean_isfs(clean_regions_table: str):
    """
    Computes ISFs for the given "clean regions" table. 
    
    A "clean regions" table represents all the clean regions in ics2 for a given 2-hour or 5-hour duration. It must contain 
    the following columns: 
        - rtime
        - bg0
        - bg1
        - bolus
    
    args: 
        clean_regions_table (str) -- Name of the "clean_regions" table to use for computing the ISFs
        
    @mileva todo: fix sql queries to prevent sql injection atttack
    """
    
    print(f"\nComputing ISF for Clean Regions Table {clean_regions_table}")
    
    ## Query
    conn = get_conn()
    curs = conn.cursor()
    
    ## Print range of data being used
    curs.execute(f'''select min(rtime), max(rtime) from {clean_regions_table}''')
    time_range = list(curs.fetchall())
    print(f"Time Range: {time_range}")
    
    ## Start ISF Computation
    curs.execute(f'''select rtime, bg0, bg1, bolus from {clean_regions_table}''')
    rows = curs.fetchall()

    skipped_incomplete = 0
    skipped_failed = 0
    completed = 0
    
    ## SET UP: buckets by time of day (24 buckets)
    buckets = {}        
    for i in range(24):
        buckets[i] = []
    
    for row in rows: 
        if incomplete(row):
            skipped_incomplete += 0
            continue
        else: 
            try: 
                rtime, bg0, bg1, bolus = row
                nudge_isf = (bg1 - bg0) / bolus
                buckets[rtime.hour].append(nudge_isf)
                completed += 1
            except Exception as e: 
                print(e)
                skipped_failed += 1
        
    ## Bucket analysis
    print("Analyzing bucketed nudge ISFs")    
    for hour in buckets: 
        try: 
            isf_vals = buckets[hour] 
                
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
                
        except Exception as e:
            pass
            print('Hour: {} could not be computed: {}', hour, e)

    print(f"skipped_incomplete: {skipped_incomplete}")
    print(f"skipped_failed: {skipped_failed}")
    print(f"completed: {completed}")
    return buckets
                

# ==========================================================================================================================================
# Nudge isfs
# The following function as written finds the nudge_isf values per bucket
# 
# Conditions (as specified at the top of the document): 
# a) No rescue carbs in the last hour
# b) Time since last meal > 2 hours
# c) CGMs and DI are not null
# The above conditions may not perfectly align with those for clean_regions
# See google docs (https://docs.google.com/document/d/17akLu24C9ik0tA6ojKXYRmnGofqcOZ2i3fuKvSHL3vM/edit) for futher specifics

def compute_nudge_isfs(window_length=3): 
    '''Computes the nudge_isf values for the given window length (in units of 5min) using the following equation: 
        ISF = (cgm_end - cgm_start) /  sum(DI over the window)
    '''
    
    conn = get_conn()
    curs = conn.cursor(MySQLdb.cursors.DictCursor)
    
    ## Query
    print("Querying ics2")
    curs.execute('''select rtime, cgm, dynamic_insulin, minutes_since_last_meal
                    from insulin_carb_smoothed_2 where YEAR(rtime) < "2021-09-19 17:25:00" order by rtime desc''')
    rows = curs.fetchall()
    print("Completed ics2 query")
    
    ## Constants
    # MIN_DI = 0.01 
    
    ## STATS
    skipped_rescue = 0  # events skipped because rescue carbs within 1 hour  
    skipped_meals = 0   # events skipped because meal within the past 2 hours  
    # skipped_di = 0   # events skipped because DI was null or was too small
    skipped_cgm = 0 # events skipped because start_cgm or end_cgm was null
    completed = 0       # events completed 

    ## SET UP: buckets by time of day (24 buckets)
    buckets = {}        
    for i in range(24):
        buckets[i] = []

    print("Iterating through rows")
    for i in range(len(rows) - window_length + 1): 
        start_row = rows[i]
        start_time, minutes_since_last_meal = start_row["rtime"], start_row["minutes_since_last_meal"]
                
        ## Check for rescue carbs within past hour
        rows_previous_hour = get_window_prior(curs, start_time)
        if any_rescue_carbs_dict(rows_previous_hour):
            skipped_rescue += 1
            continue
            
        ## Check for meals within past 2 hours
        if minutes_since_last_meal and minutes_since_last_meal <= 120: 
            skipped_meals += 1
            continue
        
        ## Compute Nudge ISF
        window = rows[i:i+window_length]

        start_cgm, end_cgm = window[0]["cgm"], window[-1]["cgm"]
        di_sum = sum(filter(None,[row["dynamic_insulin"] for row in window]))
        
        # if not di_sum or di_sum < MIN_DI: 
        #     skipped_di += 1
        #     continue

        if start_cgm and end_cgm and di_sum: 
            nudge_isf = (end_cgm - start_cgm) / di_sum
            try: 
                buckets[start_time.hour].append(nudge_isf)
                completed += 1
            except Exception as e: 
                print("Failed to add to bucket", e)
        else: 
            skipped_cgm += 1
            continue
         
    # BUCKET ANALYSIS
    print("Analyzing bucketed nudge ISFs")
    for hour in buckets: 
        try: 
            isf_vals = buckets[hour] 

            zero_count = 0 # Number of times isf = 0
            for isf_val in isf_vals:
                if isf_val == 0:
                    zero_count +=1
                
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
                
        except Exception as e:
            pass
            print('Hour: {} could not be computed: {}', hour, e)

    print(f"skipped_rescue: {skipped_rescue}")
    print(f"skipped_meals: {skipped_meals}")
    # print(f"skipped_di: {skipped_di}")
    print(f"skipped_cgm: {skipped_cgm}")
    print(f"completed: {completed}")

    return buckets

# # ================================================================

if __name__ == '__main__':
    conn = get_conn()
    
    print("\nClean 5hr ISFs")
    clean_isfs(clean_regions_table = "clean_regions_5hr_new")
    
    print("\nClean 2hr ISFs")
    clean_isfs(clean_regions_table = "clean_regions_2hr_new")
    
    print("\n15-minute nudge ISFs")
    compute_nudge_isfs(window_length=3)
