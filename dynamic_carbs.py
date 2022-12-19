"""
Provides two functions to compute and store dynamic carbs (dc) in the database: 
1. compute_dynamic_carbs: Computes dc for a single record. Use it to update the database in realtime.
2. compute_dynamic_carbs_batch: Computes dc for a batch of records. Use it to update multiple records after the fact.
Last updated on 12/19/22 by Mileva
"""

from action_curves import cache_action_curves
from predictive_model_june21 import convolve, carb_code_mapping
import cs304dbi as dbi
from datetime import datetime, timedelta
import date_ui
import pandas as pd
import time

TABLE = 'janice.insulin_carb_smoothed_2'

def get_conn():
    conn = dbi.connect()
    conn.autocommit(True)
    return conn
    
def compute_dynamic_carbs(conn, rtime):
    """Compute dynamic carbs for a single given rtime and update the database."""
    rtime = date_ui.to_datetime(rtime)
    rtime = date_ui.to_rtime(rtime)
    print("rtime", rtime)

    # Get action_curves
    action_curves, _ = cache_action_curves(conn)
    carb_action_curves = {key: action_curves[key] for key in action_curves if key != 'insulin'}

    longest_carb_curve = max([len(curve) for curve in iter(carb_action_curves.values())])

    # get all past_events from the past 6 hrs (length of longest carb curve)
    curs = dbi.dict_cursor(conn)
    curs.execute('''select rtime,
                    timestampdiff(MINUTE,%s,rtime) as delta,
                        coalesce(bg, cgm) as abg,
                        carb_code,
                        if(carbs is null, 0, carbs) as carbs,
                        rescue_carbs
                    from insulin_carb_smoothed_2
                where rtime >= %s and rtime <= %s''',
                [rtime, rtime-timedelta(minutes=(longest_carb_curve * 5)), rtime])
    past_inputs = curs.fetchall()

    # Get carb information in wide format 
    # (e.g. we represent {carb_code: “rescue”, carbs:16} as {“rescue”: 16, “brunch”:0, ..., “dinner”: 0})
    all_carb_codes = [dct['carb_code'] for dct in past_inputs]
    dummy_carb_encoding = pd.get_dummies(all_carb_codes)
    for i in range(len(past_inputs)):
        # add the dummy encoding to each row in past_inputs
        row = past_inputs[i]
        row.update(dummy_carb_encoding.iloc[i] * row['carbs'])

    # Carb_codes present in past_inputs    
    carb_codes = set([code for code in all_carb_codes if code is not None])
    
    # Compute dynamic carbs for the given time
    dynamic_carbs = 0
    for code in carb_codes:
        dynamic_carbs += convolve(past_inputs, len(past_inputs) - 1, code, action_curves[carb_code_mapping(code)])
    
    # Update the SQL table with the dynamic carbs
    curs.execute(f'''INSERT INTO {TABLE}(rtime, dynamic_carbs)
                    VALUES(%s, %s)
                    ON DUPLICATE KEY UPDATE
                    dynamic_carbs=%s''', [row['rtime'], dynamic_carbs, dynamic_carbs])
    print(row['rtime'], row['carbs'], row['carb_code'], dynamic_carbs)

    return dynamic_carbs
    
def compute_dynamic_carbs_batch(conn, rtime = None):
    """ Compute the dynamic carbs for a batch of records and update the database. 
    If rtime is None, computes the dynamic carbs for all records in the database. 
    If rtime is given, computes the dynamic carbs for all records beginning at that rtime.
    In either case, if carb records are or data is missing in the database, we assume 0 carbs were given at that time.
    Runtime for all records in the database as of 12/19/22 = 3025 seconds = 50 minutes.
    """
    
    # Get action_curves
    action_curves, _ = cache_action_curves(conn)
    carb_action_curves = {key: action_curves[key] for key in action_curves if key != 'insulin'}
    
    curs = dbi.dict_cursor(conn)
    # Gets ALL records in the database
    if rtime is None: 
        # Get the latest time from the database
        curs.execute('''select max(rtime) as currentTime from insulin_carb_smoothed_2;''')
        rtime = curs.fetchone()['currentTime']
        curs.execute('''select rtime,
                        timestampdiff(MINUTE,%s,rtime) as delta,
                            coalesce(bg, cgm) as abg,
                            carb_code,
                            if(carbs is null, 0, carbs) as carbs,
                            rescue_carbs
                        from insulin_carb_smoothed_2''', [rtime])
    # Gets records after the given time            
    else: 
        rtime = date_ui.to_datetime(rtime)
        rtime = date_ui.to_rtime(rtime)
        curs.execute('''select rtime,
                        timestampdiff(MINUTE,%s,rtime) as delta,
                            coalesce(bg, cgm) as abg,
                            carb_code,
                            if(carbs is null, 0, carbs) as carbs,
                            rescue_carbs
                        from insulin_carb_smoothed_2
                        where rtime >= %s''', [rtime, rtime])
    
    past_inputs = curs.fetchall()
    print("rtime", rtime)
    print('num past inputs', len(past_inputs))

    # Add carb information in wide format to past_inputs
    # (e.g. we represent {carb_code: “rescue”, carbs:16} as {“rescue”: 16, “brunch”:0, ..., “dinner”: 0})
    all_carb_codes = [dct['carb_code'] for dct in past_inputs]
    dummy_carb_encoding = pd.get_dummies(all_carb_codes)
    # Note: The loop below is slow and should ideally be optimized
    count = 0
    for i in range(len(past_inputs)):
        # add the dummy encoding to each row in past_inputs
        row = past_inputs[i]
        row.update(dummy_carb_encoding.iloc[i] * row['carbs'])
        if (count%100000 == 0): 
            print(f"Rows updated so far: {count}")
        count+=1
        
    # Carb_codes present in past_inputs
    carb_codes = set([code for code in all_carb_codes if code is not None])
    print('unique carb_codes', carb_codes)

    # Compute dynamic carbs for each record in past_inputs
    for i in range(len(past_inputs)):
        row = past_inputs[i]
        # Compute dynamic carbs
        dynamic_carbs = 0
        for code in carb_codes:
            dynamic_carbs += convolve(past_inputs, i, code, action_curves[carb_code_mapping(code)])
        # Update database with the result of the dynamic carb computation
        curs.execute(f'''INSERT INTO {TABLE}(rtime, dynamic_carbs)
                        VALUES(%s, %s)
                        ON DUPLICATE KEY UPDATE
                        dynamic_carbs=%s''',[row['rtime'], dynamic_carbs, dynamic_carbs])
        print(row['rtime'], row['carbs'], row['carb_code'], dynamic_carbs)

if __name__ == '__main__':
    t_start = time.time()

    ### EXAMPLES ###
    # # 1. Update a single record (e.g. '2022-12-19 13:05:00') in the database
    # conn = get_conn()
    # rtime = '2022-12-19 13:05:00'
    # compute_dynamic_carbs(conn, rtime)

    # # 2. Update all records in the database from a given time (e.g. '2022-12-19 13:05:00') onwards
    # conn = get_conn()
    # rtime = '2022-12-19 13:05:00'
    # compute_dynamic_carbs_batch(conn, rtime)
    
    # # 3. Update all records in the database
    # conn = get_conn()
    # compute_dynamic_carbs_batch(conn)
    
    t_end = time.time()
    total = t_end - t_start
    print("total time", total)
