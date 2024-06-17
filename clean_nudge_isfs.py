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
from typing import Optional

## Utils

def insert_15_min_isf(curs, rtime: str, isf: float) -> None: 
    """ Insert the specified rtime and clean 15min Nudge ISF into nudge_isf_results 
    
    todo: ideally, generalize this function to accept a column name. 
    
    args: 
        rtime (str) - rtime for the nudge ISF value being inserted into the table
        isf (float) - nudge isf value being inserted into the table
    
    """
    curs.execute('''INSERT INTO nudge_isf_results (rtime, clean_15_min) VALUES (%s, %s) ON DUPLICATE KEY UPDATE clean_15_min=VALUES(clean_15_min)''', 
                    [rtime, isf]
    )   
    
def get_clean_window(curs, start_time: str, duration: int = 2) -> list: 
    """ Get records from within clean regions
     
    Args: 
        curs - cursor
        start_time (str) - start time of clean region
        duration (int) - length of clean region in hours
     """
    if not isinstance(start_time, str): 
        start_time = str(start_time)
    sql_statement = f"select rtime, cgm, dynamic_insulin from insulin_carb_smoothed_2 where rtime >= %s and rtime <= addtime(%s, '{duration:02d}:00:00')"
    curs.execute(sql_statement, [start_time, start_time])
    return curs.fetchall()

def compute_nudge_isfs(rows: list, window_length: int=3) -> list: 
    
    '''Computes the nudge_isf values for the given window length (in units of 5min) using the following equation:
        ISF = (cgm_end - cgm_start) /  ( DI over the window - basal over the window)
        
    Assumptions: 
        steady state basal amt = 0.6 units/ hr
        minimum DI = 0.01 * window_length. This is based on the fact that previously our MIN_DI = (0.35 / 33.713) ~ 0.01
        DI over the window - basal over the window >= minimum DI
    
    Args:
        rows (list) 
        window_length (int) - number of 5" windows we use for computing the nudge ISFs (e.g. window_length = 3 corresponds to 15" Nudge ISFs)
    Output: 
        result (list) - list of (rtime, nudge_isf) tuples 
    '''
    
    results = []
    active_dis = []
    
    ## Constants - todo: verify assumptions here
    BASAL_AMT_HR = 0.6 # Assumes baseline basal of 0.6 units/ hr. Revise this to get the latest basal amt from the db
    windows_per_hour = 60 / (5 * window_length)
    basal_amt_per_window = BASAL_AMT_HR / windows_per_hour
    MIN_DI = 0.01 * window_length  

    ## stats
    skipped_di = 0   # events skipped because DI was null or was too small
    skipped_cgm = 0 # events skipped because start_cgm or end_cgm was null
    completed = 0       # events completed 
    
    for i in range(len(rows) - window_length + 1): 
        start_row = rows[i]
        start_time, start_cgm, _ = start_row
        
        ## Get the records that comprise the X-minute window for the X-minute Nudge ISFs
        window = rows[i:i+window_length]

        _, end_cgm, _ = window[-1]
        
        # Compute the active DI: sum DI over window - basal over window >= MIN_DI
        di_sum = sum(filter(None,[di for _, _, di in window]))
        active_di = di_sum - basal_amt_per_window
        active_dis.append(active_di)
        if active_di < MIN_DI: 
            skipped_di += 1
            continue
        
        # Compute Nudge ISFs
        if start_cgm and end_cgm and active_di: 
            try: 
                nudge_isf = (end_cgm - start_cgm) / active_di
                completed += 1
            except Exception as e: 
                print("Failed to compute Nudge ISF", e)
            else: 
                results.append((start_time, nudge_isf))
        else: 
            skipped_cgm += 1
            
    print(f"skipped_di = {skipped_di} \t skipped_cgm = {skipped_cgm} \t completed = {completed}")
    print(f"Active DI: avg = {np.mean(active_dis)}, min = {min(active_dis)}, max = {max(active_dis)}, ")
            
    return results

def compute_clean_nudge_isfs(curs): 
    """ Compute clean nudge ISFs and save them into the nudge_isf_results table """
    
    # Get rtimes of al the 2hr clean regions
    curs.execute('''select rtime from clean_regions_2hr_new''')
    clean_regions = curs.fetchall()
    
    # Compute the nudge ISFs for each clean region and save them in the database
    for clean_start, in clean_regions: 
        print()
        clean_rows = get_clean_window(curs, clean_start, duration=2)
        nudge_isfs = compute_nudge_isfs(clean_rows, window_length=3)
        for i, (start_time, nudge_isf) in enumerate(nudge_isfs): 
            print(f"i = {i} \t start_time = {start_time} \t nudge_isf = {nudge_isf}")
            insert_15_min_isf(curs, rtime = start_time, isf = nudge_isf)

def compute_isf_statistics(curs) -> None: 
    """ Queries the Nudge ISF table and computes statistics on the bucketed ISFs"""
    
    # Queries nudge_isf_results for all clean_15_min nudge ISFs
    curs.execute('''select rtime, clean_15_min from nudge_isf_results''')
    rows = curs.fetchall()
    
    # bucket the nudge ISF values
    buckets = {}
    for i in range(24): 
        buckets[i] = []
    
    for start_time, nudge_isf in rows: 
        try: 
            buckets[start_time.hour].append(nudge_isf)
        except Exception as e: 
            print("Failed to add to bucket", e)
            
    # compute statistics on the bucketed ISFs
    analyze_buckets(buckets)        


def analyze_buckets(buckets: dict) -> None: 
    """ Given bucketed ISFs, computes Nudge ISF statistics
        
    args: 
        buckets (dict) - ISFs bucketed by hour. The dictionary is of the form {hour: [nudge_isfs]}
    """
    for hour in buckets: 
        try: 
            isf_vals = buckets[hour] 

            count = len(isf_vals)
            zero_count = sum(1 for isf_val in isf_vals if isf_val == 0) # Number of times isf = 0
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
            print('Hour: {} could not be computed: {}', hour, e)   
            

if __name__ == '__main__':
    conn = get_conn()
    curs = conn.cursor()
    compute_clean_nudge_isfs(curs)
    compute_isf_statistics(curs)
    
