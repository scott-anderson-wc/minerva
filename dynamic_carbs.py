"""
Computes and stores dynamic carbs in the database.
Last updated on 11/26/22 by Mileva
"""

from action_curves import cache_action_curves
from predictive_model_june21 import convolve, carb_code_mapping
import cs304dbi as dbi
from datetime import datetime, timedelta
import date_ui
import pandas as pd

def get_conn():
    conn = dbi.connect()
    conn.autocommit(True)
    return conn

def compute_dynamic_carbs(conn, rtime):
    """Compute dynamic carbs for a given rtime.
    Next steps:
    1. Testing required,
    2. Update database with newest dc."""

    rtime = date_ui.to_datetime(rtime)
    rtime = date_ui.to_rtime(rtime)
    print("rtime", rtime)

    # Get action_curves
    action_curves, _ = cache_action_curves(conn)
    carb_action_curves = {key: action_curves[key] for key in action_curves if key != 'insulin'}

    longest_carb_curve = max([len(curve) for curve in iter(carb_action_curves.values())])

    # get all past_events that occurred within the duration of the longest carb curve (72 steps = 360 minutes)
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

    # Add carb information in wide format to past_inputs
    # (e.g. we represent {carb_code: “rescue”, carbs:16} as {“rescue”: 16, “brunch”:0, ..., “dinner”: 0})
    carb_codes = [dct['carb_code'] for dct in past_inputs]
    dummy_carb_encoding = pd.get_dummies(carb_codes)
    for i in range(len(past_inputs)):
        # add the dummy encoding to each row in past_inputs
        row = past_inputs[i]
        row.update(dummy_carb_encoding.iloc[i] * row['carbs'])
    print("Past Inputs")
    print(pd.DataFrame(past_inputs))

    # Carb_codes present in past_inputs
    carb_codes = set([code for code in carb_codes if code is not None])
    print('unique carb_codes', carb_codes)

    # Computes dynamic carbs if no time lapses are present
    if len(past_inputs) == (longest_carb_curve + 1):
        dynamic_carbs = 0
        for code in carb_codes:
            # index val might need to be (len(past_inputs) - 2).
            # We want the (len(past_inputs) - 1)th item at the (len(past_inputs) - 2) index?
            dynamic_carbs += convolve(past_inputs, len(past_inputs) - 1, code, action_curves[carb_code_mapping(code)])
    else:
        print(f"Time lapses present prior to {rtime}")
        dynamic_carbs = None

    return dynamic_carbs

def compute_dynamic_carbs_all(conn):
    """Compute dynamic carbs for the entire database. Testing required.
    Assumes there are no time lapses in the past inputs (incorrect assumption as of 11/26/22)"""

    # For testing we specify a time. In production, time_now = current time
    time_now = "2022-11-25 13:00:00"
    time_now = date_ui.to_datetime(time_now)
    time_now = date_ui.to_rtime(time_now)
    rtime = time_now
    print("rtime", rtime)

    # Get action_curves
    action_curves, _ = cache_action_curves(conn)
    carb_action_curves = {key: action_curves[key] for key in action_curves if key != 'insulin'}
    print("Carb_action_curves:", carb_action_curves.keys())

    # Length of longest carb action curve
    skip_amt = max([len(curve) for curve in iter(carb_action_curves.values())])
    print('skip_amt', skip_amt)

    # get all past_events. For testing we specify a shorter time window. In production, use all the data.
    curs = dbi.dict_cursor(conn)
    curs.execute('''select rtime,
                    timestampdiff(MINUTE,%s,rtime) as delta,
                        coalesce(bg, cgm) as abg,
                        carb_code,
                        if(carbs is null, 0, carbs) as carbs,
                        rescue_carbs
                    from insulin_carb_smoothed_2
                    where rtime >= %s''',
                 [rtime, rtime-timedelta(hours=3)])
    past_inputs = curs.fetchall()
    print('num past inputs', len(past_inputs))

    # Add carb information in wide format to past_inputs
    # (e.g. we represent {carb_code: “rescue”, carbs:16} as {“rescue”: 16, “brunch”:0, ..., “dinner”: 0})
    carb_entries = [dct['carb_code'] for dct in past_inputs]
    dummy_carb_encoding = pd.get_dummies(carb_entries)
    for i in range(len(past_inputs)):
        # add the dummy encoding to each row in past_inputs
        row = past_inputs[i]
        row.update(dummy_carb_encoding.iloc[i] * row['carbs'])
    # print(pd.DataFrame(past_inputs))

    # Carb_codes present in past_inputs
    carb_codes = set([dct['carb_code'] for dct in past_inputs if dct['carb_code'] is not None])
    print('unique carb_codes', carb_codes)

    # Compute dynamic carbs for all rows with enough (i.e. num steps of longest carb curve) prior data
    # This assumes there are no time lapses in the data (i.e. there is a row for each 5-minute timestep)
    rows = []
    for i in range(skip_amt, len(past_inputs)):
        row = past_inputs[i]
        # Compute dynamic carbs
        dynamic_carbs = 0
        for code in carb_codes:
            dynamic_carbs += convolve(past_inputs, i, code, action_curves[carb_code_mapping(code)])
        # Update database with dynamic carb computation
        # curs.execute('''INSERT INTO dynamic_carbs_test(rtime, dynamic_carbs)
        #                 VALUES(%s, %s)
        #                 ON DUPLICATE KEY UPDATE
        #                 dynamic_carbs=%s''', [row['rtime'], dynamic_carbs, dynamic_carbs])
        print(row['rtime'], dynamic_carbs)

if __name__ == '__main__':
    conn = get_conn()
    rtime = "2022-11-25 13:00:00"
    # rtime = "2022-11-22 13:00:00"
    dc = compute_dynamic_carbs(conn, rtime)
    print(f"Dynamic Carbs at time {rtime}: {dc}")
