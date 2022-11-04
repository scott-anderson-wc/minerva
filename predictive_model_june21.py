'''My head is swimming with the complexity of this model. I've written up my thoughts in
this Google Doc:

https://docs.google.com/document/d/1-erML0G9NQuPqN8CFUDG2M9Z4nfwIZiGpPK6noOTdRk/edit#

The inputs are

coef_bg_now,
bg_now,
coef_bg_prev,
bg_prev,
coef_effect,
insulin_inputs,
isf_function,
percent_curve,
coef_carbs,
carb_inputs

The percent curve will sum to 1.0 but the number of values will be 60,
because 60 steps times 5 minutes per step is 300 minutes or 5
hours. P[i] is the percent of a past insulin that is active at this
time. Usually, we call this the Insulin_Action_curve or IAC.

Scott

June 2021

'''

import sys
import math
import logging
from datetime import datetime, timedelta
import json
import config
import cs304dbi as dbi
import date_ui
import random

# ================================================================
# Notes are like flashing.

notes = []

def add_note(msg):
    global notes
    notes.append(msg)

def all_notes():
    global notes
    vals = notes
    notes = []
    return vals

## ================================================================


logging.basicConfig(level=logging.DEBUG) # goes to stderr?

def predictive_model_june21(time_now,
                            conn = None,
                            debug = False,
                            coef_bg_now = 1, # c0
                            bg_now = None,
                            coef_bg_prev = 0, # c1
                            bg_prev = None,
                            coef_bg_slope = 1, # c2
                            bg_slope = None,
                            coef_effect = 1, # c3
                            insulin_inputs = None,
                            basal_rate_12 = None,
                            isf_function = None,
                            percent_curve = None,
                            coef_carbs = 7,
                            carb_curve = None,
                            carb_inputs = None):

    '''Returns a prediction (a trace of BG values) for a length of time
(two hours) from the given time_now. The result is suitable for
plotting along with the actual BG values, if any. Other values have
sensible defaults but can be provided.

Defaults that are None will be read from the database or otherwise
    computed.

    '''
    time_now = date_ui.to_datetime(time_now)
    time_now = date_ui.to_rtime(time_now)
    logging.info('predictive model for {}'.format(time_now))
    add_note('predictive model for {}'.format(time_now))
    # computing defaults
    if conn is None:
        conn = dbi.connect()
    curs = dbi.dict_cursor(conn)
    if bg_now is None:
        bg_now = float(get_bg(time_now, conn=conn))
    time_prev = time_now - timedelta(minutes=5)
    if bg_prev is None:
        bg_prev = float(get_bg(time_prev, conn=conn))
    # we may eventually replace this bg_slope with, say, a 30-minute slope
    if bg_slope is None:
        bg_slope = bg_now - bg_prev
    # insulin processing
    if insulin_inputs is None:
        # value is a list of tuples
        vals = get_past_insulin_at_time(time_now, conn=conn)
        insulin_inputs = [ t[1] for t in vals ]
        past_rtimes = [ t[0] for t in vals ]
        ok = (type(insulin_inputs) is list and len(insulin_inputs) == 60)
        if not ok:
            add_note("prediction failed because we don't have a list of 60 past insulin inputs")
            return [], [], [], [], [], all_notes()
        # assert(type(insulin_inputs) is list and len(insulin_inputs) == 60)
    if basal_rate_12 is None:
        basal_rate_12 = get_basal_rate_12(time_now, conn=conn)
        add_note('using basal_rate_12 of '+str(basal_rate_12))
    if isf_function is None:
        isf_function = estimated_isf
    logging.debug('initial ISF %s', isf_function(time_now))
    add_note('initial ISF %s'.format(isf_function(time_now)))
    # the percent curve is our IAC
    if percent_curve is None:
        percent_curve = getIAC(conn=conn)
        ok = (type(percent_curve) is list and len(percent_curve) == 60)
        if not ok:
            add_note('prediction failed because IAC curve is not a list of 60 numbers')
            return [], [], [], [], [], all_notes()
        # assert(type(percent_curve) is list and len(percent_curve) == 60)
        percent_curve.reverse()
    # carb processing
    if carb_inputs is None:
        carb_inputs = get_past_carbs_at_time(time_now, conn=conn)
        ok = (type(carb_inputs) is list and len(carb_inputs) == 60)
        if not ok:
            add_note("prediction failed because we don't have a list of 60 past carb inputs")
            return [], [], [], [], [], all_notes()
        # assert(type(carb_inputs) is list and len(carb_inputs) == 60)
    if carb_curve is None:
        carb_curve = normalize(CAC) # returns a new list
        # omit the length check. It'll be 40 and will run out when we
        # do the convolution, but that's okay
        ok = (type(carb_curve) is list)
        if not ok:
            add_note("prediction failed because we don't have carb curve")
            return [], [], [], [], [], all_notes()
        # assert(type(carb_curve) is list)
        carb_curve.reverse()
    # outputs, predictions (bg units) dynamic insulin and dynamic carbs
    predictions = []
    di_values = []
    dc_values = []
    di_deltas = []
    dc_deltas = []
    prev_di = 0
    prev_dc = 0
    for pt in range(20):
        # this is the convolution
        dynamic_insulin = sum([x * y for x,y in zip(insulin_inputs, percent_curve)])
        # this is a bit much for the notes
        logging.debug('dynamic_insulin: %s', dynamic_insulin)
        effect = -1 * dynamic_insulin * isf_function(time_now)
        dynamic_carbs = sum([x * y for x,y in zip(carb_inputs, carb_curve)])
        rt = past_rtimes[pt]
        logging.debug('RT: %s PM: %d IN: %d BG %.2f DI %.2f Effect %.2f DC: %.2f ',
                      rt,
                     pt,
                      insulin_inputs[0],
                     bg_now,
                     dynamic_insulin,
                     effect,
                     dynamic_carbs)
        bg_next = (coef_bg_now * bg_now +
                   coef_bg_prev * bg_prev +
                   coef_effect * effect +
                   coef_carbs * dynamic_carbs )
        predictions.append(bg_next)
        # insulin
        di_values.append(dynamic_insulin)
        delta_di, prev_di = dynamic_insulin - prev_di, dynamic_insulin
        di_deltas.append(delta_di)
        # carbs
        dc_values.append(dynamic_carbs)
        delta_dc, prev_dc = dynamic_carbs - prev_dc, dynamic_carbs
        dc_deltas.append(delta_dc)
        # drop the oldest insulin and append the basal rate onto the
        # end as the newest value. This is not efficient coding, but
        # we can revisit this some other time and implement a circular
        # buffer
        # print('B: '+','.join(map(str,insulin_inputs)))
        insulin_inputs.append(basal_rate_12)
        insulin_inputs.pop(0)
        # rotate the carbs, too
        carb_inputs.append(0)
        carb_inputs.pop(0)
        # print('A: '+','.join(map(str,insulin_inputs)))
        # Advance now and past
        (bg_now, bg_past, time_now) = (bg_next, bg_now, time_now+timedelta(minutes=5))
    return predictions, di_values, dc_values, di_deltas, dc_deltas, all_notes()

## ================================================================ New Algorithm

def none_zero(x):
    return 0 if x is None else x

def predictive_model_sept21(time_now,
                            conn = None,
                            debug = False,
                            coef_bg_now = 1, # c0
                            bg_now = None,
                            coef_bg_prev = 0, # c1
                            bg_prev = None,
                            coef_bg_slope = 1, # c2
                            bg_slope = None,
                            coef_effect = 1, # c3
                            past_inputs = None,
                            insulin_inputs = None,
                            basal_rate_12 = None,
                            isf_function = None,
                            iac_curve = None,
                            coef_carbs = 7,
                            carb_curve = None,
                            carb_inputs = None):

    '''Returns a prediction (a trace of BG values) for a length of time
(two hours) from the given time_now. The result is suitable for
plotting along with the actual BG values, if any. Other values have
sensible defaults but can be provided.

Defaults that are None will be read from the database or otherwise
    computed.

This one differs in getting a bunch of past data as dictionaries,
iterating over it to make the predictions, and adding the prediction
to the dictionary. Then converting to a table, for easier analysis.

    '''
    time_now = date_ui.to_datetime(time_now)
    time_now = date_ui.to_rtime(time_now)
    logging.info('predictive model for {}'.format(time_now))
    # computing defaults
    if conn is None:
        conn = dbi.connect()
    curs = dbi.dict_cursor(conn)
    if bg_now is None:
        bg_now = float(get_bg(time_now, conn=conn))
    time_prev = time_now - timedelta(minutes=5)
    if bg_prev is None:
        bg_prev = float(get_bg(time_prev, conn=conn))
    # we may eventually replace this bg_slope with, say, a 30-minute slope
    if bg_slope is None:
        bg_slope = bg_now - bg_prev
    rtime = time_now
    if past_inputs is None:
        # need carbs and insulin to compute DC and DI
        # need rtime and delta time for x-axis
        # need abg (actual bg) for comparison to prediction
        curs.execute('''select rtime,
                        timestampdiff(MINUTE,%s,rtime) as delta,
                           coalesce(bg, cgm) as abg,
                           if(total_bolus_volume is null,basal_amt_12,total_bolus_volume+basal_amt_12) as insulin,
                           if(carbs is null, 0, carbs) as carbs,
                           rescue_carbs,
                           basal_amt_12
                    from insulin_carb_smoothed_2
                    where rtime >= %s and rtime <= %s''',
                 [rtime, rtime-timedelta(hours=5), rtime+timedelta(hours=3)])
        past_inputs = curs.fetchall()
    if basal_rate_12 is None:
        # should get this from past_inputs instead
        basal_rate_12 = get_basal_rate_12(time_now, conn=conn)
    if isf_function is None:
        isf_function = estimated_isf
    logging.debug('initial ISF %s', isf_function(time_now))
    # the percent curve is our IAC
    if iac_curve is None:
        iac_curve = getIAC(conn=conn)
        assert(type(iac_curve) is list and len(iac_curve) == 60)
        # iac_curve.reverse()
    if carb_curve is None:
        carb_curve = normalize(CAC)
        # omit the length check. It'll be 40 and will run out when we
        # do the convolution, but that's okay
        assert(type(carb_curve) is list)
        # carb_curve.reverse()
    # outputs, predictions (bg units) dynamic insulin and dynamic carbs
    predictions = []
    prev_di = 0
    prev_dc = 0
    # New algorithm. Skip the first N rows because we need N past
    # inputs to compute DC and DI. N = max(len(percent_curve), len(carb_curve))
    skip_amt = max(len(iac_curve), len(carb_curve))
    skip_rows = past_inputs[0:skip_amt]
    print('initial insulin inputs',insulin_inputs)
    print('initial carb inputs',carb_inputs)
    for i in range(skip_amt, len(past_inputs)):
        row = past_inputs[i]
        dynamic_insulin = convolve(past_inputs, i, 'insulin', iac_curve)
        effect = -1 * dynamic_insulin * isf_function(time_now)
        dynamic_carbs = convolve(past_inputs, i, 'carbs', carb_curve)
        rt = row['rtime']
        logging.debug('RT: %s DT: %s IN: %d BG %.2f DI %.2f Effect %.2f DC: %.2f ',
                      rt, row['delta'],
                      row['insulin'],
                      bg_now,
                      dynamic_insulin,
                      effect,
                      dynamic_carbs)
        bg_next = (coef_bg_now * bg_now +
                   coef_bg_prev * bg_prev +
                   coef_effect * effect +
                   coef_carbs * dynamic_carbs )
        predictions.append(bg_next)
        row['pred_bg'] = bg_next
        row['di'] = dynamic_insulin
        row['dc'] = dynamic_carbs
        delta_di, prev_di = dynamic_insulin - prev_di, dynamic_insulin
        row['delta_di'] = delta_di
        # carbs
        delta_dc, prev_dc = dynamic_carbs - prev_dc, dynamic_carbs
        row['delta_dc'] = delta_dc
        # Advance now and past
        (bg_now, bg_past, time_now) = (bg_next, bg_now, time_now+timedelta(minutes=5))
    return predictions, past_inputs

pm = predictive_model_june21

# ================================================================
# Predictive Model with multiple carbs

def predictive_model_multi_carbs(
        time_now,
        conn = None,
        debug = False,
        coef_bg_now = 1, # c0
        bg_now = None,
        coef_bg_prev = 0, # c1
        bg_prev = None,
        coef_bg_slope = 1, # c2
        bg_slope = None,
        coef_effect = 1, # c3
        past_inputs = None,
        insulin_inputs = None,  # replace with past_inputs?
        basal_rate_12 = None,
        isf_function = None,
        action_curves = None,   # added this (from action_curves.py)
        iac_curve = None,       # replace by action_curves
        coef_carbs = 7,         # do we still want this?
        carb_curve = None,      # replace by action_curves
        # probably want to delete carb_inputs and use past_inputs instead
        carb_inputs = None):

    '''Returns a prediction (a trace of BG values) for a length of time
(two hours) from the given time_now. The result is suitable for
plotting along with the actual BG values, if any. Other values have
sensible defaults but can be provided.

Defaults that are None will be read from the database or otherwise
    computed.

This PM tries to identify the kind of carbs (brunch, dinner or rescue)
and use the appropriate curve. It uses the curves read from the
database tables by functions in action_curves.py.

This one gets a bunch of past data as dictionaries, iterating over it
to make the predictions, and adding the prediction to the
dictionary. Then converting to a table, for easier analysis.
    '''
    time_now = date_ui.to_datetime(time_now)
    time_now = date_ui.to_rtime(time_now)
    logging.info('predictive model for {}'.format(time_now))
    # computing defaults
    if conn is None:
        conn = dbi.connect()
    curs = dbi.dict_cursor(conn)
    if bg_now is None:
        bg_now = float(get_bg(time_now, conn=conn))
    time_prev = time_now - timedelta(minutes=5)
    if bg_prev is None:
        bg_prev = float(get_bg(time_prev, conn=conn))
    # we may eventually replace this bg_slope with, say, a 30-minute slope
    if bg_slope is None:
        bg_slope = bg_now - bg_prev
    rtime = time_now
    if past_inputs is None:
        # need carbs and insulin to compute DC and DI
        # need rtime and delta time for x-axis
        # need abg (actual bg) for comparison to prediction
        # added carb_code so we can know which action curve to apply
        curs.execute('''select rtime,
                        timestampdiff(MINUTE,%s,rtime) as delta,
                           coalesce(bg, cgm) as abg,
                           if(total_bolus_volume is null,basal_amt_12,total_bolus_volume+basal_amt_12) as insulin,
                           carb_code,
                           if(carbs is null, 0, carbs) as carbs,
                           rescue_carbs,
                           basal_amt_12
                    from insulin_carb_smoothed_2
                    where rtime >= %s and rtime <= %s''',
                 [rtime, rtime-timedelta(hours=5), rtime+timedelta(hours=3)])
        past_inputs = curs.fetchall()
    if basal_rate_12 is None:
        # should get this from past_inputs instead
        basal_rate_12 = get_basal_rate_12(time_now, conn=conn)
    if isf_function is None:
        isf_function = estimated_isf
    logging.debug('initial ISF %s', isf_function(time_now))
    # the percent curve is our IAC
    if iac_curve is None:
        iac_curve = getIAC(conn=conn)
        assert(type(iac_curve) is list and len(iac_curve) == 60)
        # iac_curve.reverse()
    if carb_curve is None:
        carb_curve = normalize(CAC)
        # omit the length check. It'll be 40 and will run out when we
        # do the convolution, but that's okay
        assert(type(carb_curve) is list)
        # carb_curve.reverse()
    # outputs, predictions (bg units) dynamic insulin and dynamic carbs
    predictions = []
    prev_di = 0
    prev_dc = 0
    # New algorithm. Skip the first N rows because we need N past
    # inputs to compute DC and DI. N = max(len(percent_curve), len(carb_curve))
    skip_amt = max(len(iac_curve), len(carb_curve))
    skip_rows = past_inputs[0:skip_amt]
    print('initial insulin inputs',insulin_inputs)
    print('initial carb inputs',carb_inputs)
    for i in range(skip_amt, len(past_inputs)):
        row = past_inputs[i]
        dynamic_insulin = convolve(past_inputs, i, 'insulin', iac_curve)
        effect = -1 * dynamic_insulin * isf_function(time_now)
        dynamic_carbs = convolve(past_inputs, i, 'carbs', carb_curve)
        rt = row['rtime']
        logging.debug('RT: %s DT: %s IN: %d BG %.2f DI %.2f Effect %.2f DC: %.2f ',
                      rt, row['delta'],
                      row['insulin'],
                      bg_now,
                      dynamic_insulin,
                      effect,
                      dynamic_carbs)
        bg_next = (coef_bg_now * bg_now +
                   coef_bg_prev * bg_prev +
                   coef_effect * effect +
                   coef_carbs * dynamic_carbs )
        predictions.append(bg_next)
        row['pred_bg'] = bg_next
        row['di'] = dynamic_insulin
        row['dc'] = dynamic_carbs
        delta_di, prev_di = dynamic_insulin - prev_di, dynamic_insulin
        row['delta_di'] = delta_di
        # carbs
        delta_dc, prev_dc = dynamic_carbs - prev_dc, dynamic_carbs
        row['delta_dc'] = delta_dc
        # Advance now and past
        (bg_now, bg_past, time_now) = (bg_next, bg_now, time_now+timedelta(minutes=5))
    return predictions, past_inputs

def make_test_inputs(start_time, duration, events):
    '''Create some test inputs for the predictive model, to supply as past_inputs value.
Given arguments like start_time='2022-11-04 06:00' and duration=3*60, and events as a list of tuples the columns
we need for computing past inputs, namely

delta     (minutes since start_time)
abg       (we'll omit this, and just use 120)
insulin
carb_code
carbs
rescue_carbs  (seems redundant. omitted)
basal_amt_12   (we'll just use a default value for now)

This computes a series of dictionaries to replace this:

        select rtime,
                        timestampdiff(MINUTE,%s,rtime) as delta,
                           coalesce(bg, cgm) as abg,
                           if(total_bolus_volume is null,basal_amt_12,total_bolus_volume+basal_amt_12) as insulin,
                           carb_code,
                           if(carbs is null, 0, carbs) as carbs,
                           rescue_carbs,
                           basal_amt_12
                    from insulin_carb_smoothed_2

'''
    start_rtime = date_ui.to_rtime(start_time)
    default_abg = 120
    default_basal = 0.1
    # first generate basic rows. We'll edit them next
    rows = [ {'rtime': start_rtime + timedelta(minutes=n),
              'delta': n,
              'abg': default_abg,
              'carb_code': None,
              'carbs': 0,
              'basal_amt_12': default_basal }
             for n in range(0, duration, 5) ]
    print('len(rows)', len(rows))
    # now iterate over events and update
    for evt in events:
        # this is the format of the events
        (dt, insulin, carb_code, carbs ) = evt
        matches = [ row for row in rows if row.get('delta') == dt ]
        if len(matches) != 1:
            # this should always match exactly one row
            raise Exception('should be only one match: {}'.format(len(matches)))
        row = matches[0]
        if insulin is not None:
            row['insulin'] = insulin
        if carb_code is not None:
            row['carb_code'] = carb_code
            row['carbs'] = carbs
    print('len(rows)', len(rows))
    return rows

def test_inputs_1():
    rows = make_test_inputs('2022-11-03 07:00', 180,
                            [(5, 2, None, None), # 2 units insulin first
                             (10, 0, 20, 'breakfast')])
    return rows

def test_pm_1():
    '''First test case for the PMMC (predictive model multi carb). This
case is a "normal" breakfast with carbs and insulin.'''
    time_now = '2022-11-03 07:00'
    duration = 180
    past = make_test_inputs(time_now, duration,
                            [(5, 2, None, None), # 2 units insulin first
                             (10, 0, 20, 'breakfast')])
    return predictive_model_multi_carbs(time_now,
                                        debug = True,
                                        past_inputs = past,
                                        basal_rate_12 = 0.1)

# ================================================================
# convolution

def convolve(list_of_rows, index, key, curve):
    '''Computes the convolution of the curve starting at index and working
backwards until either the rows run out or the curve does. Returns the
result; it's up to the caller to store it. The curve should *not* be
time-reversed. The algorithm goes back in time, interating forward in
the curve and backwards through the rows.

    '''
    sum = 0
    for j in range(len(curve)):
        # j goes from 0 to len(curve)-1 but we will work with i-j for
        # the row index, so the convolution will include the current
        # time step, but the curves talk about the immediate effect
        # (which is always zero anyhow).
        if index - j < 0:
            # out of past rows, so return
            break
        row = list_of_rows[index - j]
        prod = row[key] * curve[j]
        # print(row['delta'], '\t', row[key],'\t', curve[j], '\t', prod)
        sum += row[key] * curve[j]
    return sum

def dict_to_list(dic):
    '''returns a list using the keys in sorted order'''
    return [ dic[key] for key in sorted(dic.keys()) ]

def test_convolve(test):
    def gen_rows(n, val=0):
        return [ {'row': i, 'x': val} for i in range(n) ]
    # test 1
    if test == 1 :
        curve1 = [ 0.0, 0.4, 0.3, 0.2, 0.1, 0.0 ]
        rows1 = gen_rows(20)
        rows1[3]['x'] = 2
        for i in range(3,20):
            rows1[i]['y'] = convolve(rows1, i, 'x', curve1)
    # test 2
    if test == 2:
        curve1 = [ 0.0, 0.4, 0.3, 0.2, 0.1, 0.0 ]
        rows1 = gen_rows(30, 0.1)
        for i in range(0,30):
            rows1[i]['y'] = convolve(rows1, i, 'x', curve1)
    # output
    table = [ dict_to_list(row) for row in rows1 ]
    tsv_table_out(table)

# ================================================================
# get_bg

def get_bg(datetime, conn=None, null_okay = False):
    '''BG comes from a finger stick and is preferable to CGM when it's available.
CGM comes from the implanted meter and is more likely to be available. Sometimes
both are missing.'''
    rtime = date_ui.to_rtime(datetime)
    if conn is None:
        conn = dbi.connect()
    curs = dbi.cursor(conn)
    curs.execute('''SELECT bg, cgm
                    FROM insulin_carb_smoothed_2
                    WHERE rtime = %s''',
                 [rtime])
    row = curs.fetchone()
    if row is None:
        raise Exception('no data for datetime {} (rtime {})'.format(datetime, rtime))
    bg, cgm = row
    if bg is not None:
        return bg
    if cgm is not None:
        return cgm
    if null_okay:
        return None
    raise Exception('no BG or CGM data for datetime {} (rtime {})'.format(datetime, rtime))

def get_basal_rate_12(datetime, conn=None, null_okay = False):
    '''Basal rate is a steady input of insulin and needs to be taken into
account in the predictive model. We use basal_rate_12 because that's
non-null and is divided by 12 because the basal is spread out over the
hour.
    '''
    rtime = date_ui.to_rtime(datetime)
    if conn is None:
        conn = dbi.connect()
    curs = dbi.cursor(conn)
    curs.execute('''SELECT basal_amt_12
                    FROM insulin_carb_smoothed_2
                    WHERE rtime = %s''',
                 [rtime])
    row = curs.fetchone()
    if row is None:
        raise Exception('no data for datetime {} (rtime {})'.format(datetime, rtime))
    basal = row[0]
    if basal is not None:
        return basal
    if null_okay:
        return None
    raise Exception('no basal data for datetime {} (rtime {})'.format(datetime, rtime))


# ================================================================
# ISF from TSV

'''In the isf2.py file, we calculated medians of buckets from recent
ISF values and wrote to stdout in TSV format using the est_isf_table()
function. This code reads that file back in (or an equivalent file).
The data is also in the isf_est table.

The format is as written out by isf2.est_isf_table:
Columns are year,quarter,bucket,isf,option,n
where option are how the data was computed and
n is the number of real values that the median is
computed from.

The data is stored in memory in a dictionary where the key is

    key = (bucket, year, quarter)

and the values are (isf, option, count).

This is the same as isf2.isf_est_cache  and as computed by isf2.compute_estimated_isf_at_time.

Note that we still have a lot of failures, so we'll need to come up
with some kind of ISF value that we can use no matter what.

In the short run, I'm going to use a "smoothed" set of data
'''

SMOOTHED_ISF_VALUES = [
    # 'BUCKET', 'smooth avg ISF'
    [0, 5.0],
    [2, 10.0],
    [4, 14.0],
    [6, 18.0],
    [8, 22.0],
    [10, 25.0],
    [12, 22.0],
    [14, 19.0],
    [16, 16.0],
    [18, 13.0],
    [20, 10.0],
    [22, 7.0]
]

SMOOTHED_ISF = None

def datetime_quarter(dt):
    '''returns the quarter: 1-4'''
    return 1+(dt.month-1)//3

def datetime_bucket(dt):
    '''returns the bucket: 0-22'''
    return dt.hour//2*2

def estimated_isf_smoothed(timestamp):
    '''Returns the estimated ISF for the given timestamp using a smoothed model'''
    bucket = datetime_bucket(timestamp)
    half_bucket = bucket // 2
    return SMOOTHED_ISF_VALUES[half_bucket][1]

def estimated_isf(timestamp):
    '''The main entry point for estimating ISF. Calls different specialty
functions depending on how we want to estimate ISF.'''
    dt = date_ui.to_datetime(timestamp)
    if config.PM_ISF_SOURCE == config.PM_ISF_HISTORY_THEN_SMOOTHED:
        hist = get_isf_history()
        year, quarter, bucket = dt.year, datetime_quarter(dt), datetime_bucket(dt)
        key = (year, quarter, bucket)
        if key in hist:
            return hist[key]
        else:
            return estimated_isf_smoothed(timestamp)
    elif config.PM_ISF_SOURCE == config.PM_SMOOTHED_ONLY:
        bucket = datetime_bucket(dt)
        return SMOOTHED_ISF_VALUES[bucket]
    else:
        raise Exception('unknown value for config.PM_ISF_SOURCE: {}'
                        .format(config.PM_ISF_SOURCE))

# Historical data, bucketized, etc. This is an memory cache of the isf_est table.

ISF_EST_CACHE = None

def get_isf_history(conn = None):
    '''Read the historical ISF data from the est_ in TSV format from the given
filename. See file for more detail. Data is saved to a global dictionary, where the key is
year,quarter,bucket and the return value is a list of [isf, quality, count].'''
    global ISF_EST_CACHE
    if ISF_EST_CACHE is None:
        if conn is None:
            conn = dbi.connect()
        curs = dbi.cursor(conn)
        ISF_EST_CACHE = {}
        curs.execute('''SELECT year, quarter, time_bucket, isf_est
                        FROM isf_est''')
        for row in curs.fetchall():
            year, quarter, bucket, val = row
            key = (year, quarter, bucket)
            ISF_EST_CACHE[key] = val
    return ISF_EST_CACHE

TSV_DATA_TABLE = None

def read_isf_table(isf_filename_tsv):
    '''Read the historical ISF data in TSV format from the given
filename. See file for more detail. Data is saved to a global dictionary, where the key is
year,quarter,bucket and the return value is a list of [isf, quality, count].'''
    pass

def estimate_isf_from_tsv(timestamp):
    '''Returns the estimated ISF for the given timestamp using historical
data stored in a TSV file and cached in an in-memory table
(dictionary).'''
    pass


# ================================================================

'''IAC calculations. We know that we want to be able to adjust the IAC
with experience (machine learning, customizing the IAC to better fit
each patient). So, other than having a decent starting point, the beta
curve is irrelevant. Instead, we'll want a set of values that we can
read from a database table. We will make them add to 100 percent.

I've created a database table called IAC. We probably want to keep
historical values of IAC as we introduce machine learning, so the
columns are user, curve_date, curve and notes. The 'curve' value is just
text, and we'll parse it as json and create an array of floats.

The following variable is an in-memory cache of that database table.
'''

IAC = None

def getIAC(conn=None):
    global IAC
    if IAC is None:
        if conn is None:
            conn = dbi.connect()
        curs = dbi.dict_cursor(conn)
        user = 'hugh'
        curs.execute('''SELECT max(curve_date) as curve_date
                        FROM insulin_action_curve
                        WHERE user = %s''',
                     [user])
        curve_date = curs.fetchone()['curve_date']
        curs.execute('''select curve from insulin_action_curve
                        WHERE user=%s and curve_date=%s''',
                     [user, curve_date])
        data = curs.fetchone()['curve']
        IAC = json.loads(data)
        total = sum(IAC)
        logging.info('IAC: read {} datapoints as insulin_action_curve from {} summing to {}'
                     .format(len(IAC), curve_date, total))
    # return a copy, so that any reversal doesn't change the cached copy
    return IAC[:]


def putIAC(notes, conn=None):
    if IAC is None:
        raise Exception('''Can't put missing IAC curve''')
    if conn is None:
        conn = dbi.connect()
    curs = dbi.dict_cursor(conn)
    user = 'hugh'
    data = json.dumps(IAC)
    curs.execute('''INSERT INTO insulin_action_curve(user, curve_date, curve, notes)
                    VALUES (%s, now(), %s, %s)''',
                 [user, data, notes])
    conn.commit()

# See https://docs.google.com/spreadsheets/d/1GgIxGUKSbr854oFqOEwJ-vzbNkfV_eMLVOdqlCDAjRU/edit#gid=1055025929

BETA_CURVE = [
    0.0000,
    0.0040,
    0.0113,
    0.0175,
    0.0229,
    0.0274,
    0.0312,
    0.0342,
    0.0366,
    0.0384,
    0.0397,
    0.0405,
    0.0409,
    0.0409,
    0.0406,
    0.0399,
    0.0391,
    0.0380,
    0.0367,
    0.0353,
    0.0337,
    0.0321,
    0.0304,
    0.0286,
    0.0268,
    0.0250,
    0.0232,
    0.0215,
    0.0197,
    0.0180,
    0.0164,
    0.0149,
    0.0134,
    0.0120,
    0.0106,
    0.0094,
    0.0082,
    0.0072,
    0.0062,
    0.0053,
    0.0045,
    0.0038,
    0.0031,
    0.0026,
    0.0021,
    0.0017,
    0.0013,
    0.0010,
    0.0007,
    0.0005,
    0.0004,
    0.0003,
    0.0002,
    0.0001,
    0.0001,
    0.0000,
    0.0000,
    0.0000,
    0.0000,
    0.0000
    ]

def initIAC():
    global IAC
    IAC = BETA_CURVE
    putIAC('initial beta curve')

# ================================================================
# Carb Action Curve

'''At the moment, we have no model for how carbs get absorbed: that
is, how BG at a later time depends on Carbs at an earlier time:

BG(t+k) = f( Carbs(t) )

'''

def get_clean_rescues(conn = None, time_interval=6, loglevel=10):
    '''Returns a rescue carbs event that is 'clean' in the sense that
there were no additional carbs given, and no additional bolus of
insulin. Returns a list of tuples, with the rtime and the number
of rescue carbs given.'''
    logging.getLogger().setLevel(loglevel)
    conn = conn if conn else dbi.connect()
    curs = dbi.cursor(conn)
    curs.execute('''select rtime, carbs from insulin_carb_smoothed_2
                    where rescue_carbs = 1''')
    clean_rescues = []
    for rescue_row in curs.fetchall():
        rescue_time, rescue_carbs = rescue_row
        t1 = date_ui.mysql_datetime_to_python_datetime(rescue_time)
        t2 = t1 + timedelta(hours=time_interval)
        rescue_time_end = date_ui.python_datetime_to_mysql_datetime(t2)
        curs2 = dbi.dict_cursor(conn)
        # relevant data for the next 6 hours
        curs2.execute('''select rtime, rescue_carbs, carbs, total_bolus_volume
                                       from insulin_carb_smoothed_2
                                       where rtime >= %s and rtime <= %s''',
                                    [rescue_time, rescue_time_end])
        rescue_data = curs2.fetchall()
        second_rescue_carbs = list(filter(lambda row: row['rescue_carbs'], rescue_data))
        if len(second_rescue_carbs) > 1:
            logging.info('rescue {} has additional rescue_carbs'.format(rescue_time))
            logging.debug(tsv_dict_table_str(second_rescue_carbs))
            continue
        second_carbs = list(filter(lambda row: row['carbs'], rescue_data))
        if len(second_carbs) > 1:
            logging.info('rescue {} has additional carbs'.format(rescue_time))
            logging.debug(tsv_dict_table_str(second_carbs))
            continue
        bolus = list(filter(lambda row: row['total_bolus_volume'], rescue_data))
        if len(bolus) > 0:
            logging.info('rescue {} has additional boluses'.format(rescue_time))
            logging.debug(tsv_dict_table_str(bolus))
            continue
        clean_rescues.append(rescue_row)
    print('found {} clean rescues'.format(len(clean_rescues)))
    return clean_rescues

def actual_cac(rtime, carbs, conn = None, time_interval = 6, loglevel = 10):
    '''Trying to find an actual Carb-Action-Curve. Returns a trace of
bg_deltas for a given rtime, where the delta is measured as the
difference of the actual BG from the BG at 'rtime'. This trace is
divided by the number of carbs that were given at 'rtime' so the trace
is a delta per unit of carbs.
    '''
    rescue_time = rtime
    rescue_carbs = carbs
    t1 = date_ui.mysql_datetime_to_python_datetime(rescue_time)
    t2 = t1 + timedelta(hours=time_interval)
    rescue_time_end = date_ui.python_datetime_to_mysql_datetime(t2)

    logging.getLogger().setLevel(loglevel)
    conn = conn if conn else dbi.connect()
    curs = dbi.cursor(conn)
    # Get all BG values
    curs.execute('''select coalesce(bg, cgm) from insulin_carb_smoothed_2
                    where rtime >= %s and rtime <= %s''',
                 [rescue_time, rescue_time_end])
    bg_vals = [ row[0] for row in curs.fetchall() ]
    bg_nulls = list(filter(lambda bg: bg is None, bg_vals))
    if len(bg_nulls) > 0:
        logging.warning('%s BG values are null', len(bg_nulls))
        return None
    baseline = bg_vals[0]
    if baseline is None:
        return None
        raise Exception('no baseline bg', rtime)
    # mod to divide by carbs
    bg_deltas = [ (bg - baseline) / rescue_carbs if bg else None
                  for bg in bg_vals ]
    return bg_deltas

def stats(lst):
    n = len(lst)
    lst = sorted(lst)
    mean = sum(lst)/n
    med = lst[n//2]
    std = math.sqrt(sum([ (x-mean)*(x-mean) for x in lst ]) / (n-1))
    return [ mean, med, std, n ]

def smooth(trace):
    '''Do some local Gaussian smoothing of a curve, replacing each point
with g(x) = 0.25f(x-1) + 0.5f(x) + 0.25f(x+1). The first and last
points are not replaced.
    '''
    smoothed = []
    end = len(trace)-1
    for index in range(len(trace)):
        if index == 0:
            smoothed.append(trace[0])
        elif index == end:
            smoothed.append(trace[-1])
        else:
            smoothed.append( 0.25 * trace[index-1] +
                             0.50 * trace[index] +
                             0.25 * trace[index+1] )
    return smoothed

def usable_cac(conn = None, time_interval = 6, loglevel = logging.INFO):
    # the traces are lists where element i is the delta between bg and
    # the baseline bg at time t*i from the beginning, namely rt
    # OR, the return value is None, because something went wrong
    traces = [ actual_cac(rt, rc, conn = conn, time_interval = time_interval)
               # rt = rescue_time, rc=rescue_carbs
               for rt,rc in get_clean_rescues(conn = conn, time_interval = time_interval, loglevel = loglevel) ]
    # each trace is for the same time interval, so they have the same length, unless
    # the trace is None
    # 219 traces
    # print('len(traces)', len(traces))
    # good traces are not None, but lists of numbers
    good_traces = list(filter(lambda x: x, traces))
    # 39 good traces
    # print('len(good_traces)', len(good_traces))
    # they should all have the same length
    # all 73 elements long
    # print('lengths', list(map(len,good_traces)) )
    # the first trace is, hopefully, representative
    # print('first good trace', good_traces[0])
    # transpose means that element i is the list of deltas for step i
    trace_of_lists = transpose(good_traces)
    # the first list of deltas is all zeros
    # print('first delta', trace_of_lists[0])
    # the second list of deltas should be small
    print('second delta', trace_of_lists[1])
    print('third delta', trace_of_lists[2])
    print('stats second delta', stats(trace_of_lists[1]))
    print('stats third delta', stats(trace_of_lists[2]))
    trace_of_summaries = [ stats(lst) for lst in trace_of_lists ]
    trace_of_means = [ lst[0] for lst in trace_of_summaries ]
    smoothed1 = smooth(trace_of_means)
    return trace_of_lists, trace_of_summaries, trace_of_means, smoothed1

# ================================================================

def get_past_insulin_at_time(time_now, time_interval_hours = 5, conn=None):
    '''returns the insulin inputs for the past time_interval. These can be used
to compute dynamic insulin by convolving it with the IAC. Ultimately, we will
pre-compute these, but for now, while we are developing the predictive model,
let's just read the data.'''
    if conn is None:
        conn = dbi.connect()
    curs = dbi.cursor(conn)
    time_now = date_ui.to_rtime(time_now)
    time_prev = time_now - timedelta(hours=time_interval_hours)
    curs.execute('''SELECT rtime, basal_amt_12, total_bolus_volume
                    FROM insulin_carb_smoothed_2
                    WHERE %s < rtime and rtime <= %s
                    ORDER BY rtime''',
                 [date_ui.python_datetime_to_mysql_datetime(time_prev),
                  date_ui.python_datetime_to_mysql_datetime(time_now)])
    raw_rows = curs.fetchall()
    logging.debug('first past insulin %s', raw_rows[0])
    logging.debug('last past insulin %s', raw_rows[-1])
    ## do we have to worry about rows where *both* basal and bolus are NULL?
    ## this is a list of tuples
    vals = [ (date_ui.str(row[0]),
              (row[1] if row[1] is not None else 0)
              +
              (row[2] if row[2] is not None else 0))
             for row in raw_rows ]
    logging.debug('all past insulin %s', vals)
    max_in = max([ v[1] for v in vals])
    logging.debug('max past insulin %s', max_in)
    logging.debug('max event of past insulin %s', [ v for v in vals if v[1] == max_in ])
    logging.debug('len past insulin values %s', len(vals))
    return vals

def get_past_carbs_at_time(time_now, time_interval_hours = 5, conn=None):
    '''returns the carb inputs for the past time_interval. These can be used
to compute dynamic carbs by convolving it with the CAC. Ultimately, we will
pre-compute these, but for now, while we are developing the predictive model,
let's just read the data.'''
    conn = conn or dbi.connect()
    curs = dbi.cursor(conn)
    time_now = date_ui.to_rtime(time_now)
    time_prev = time_now - timedelta(hours=time_interval_hours)
    curs.execute('''SELECT carbs
                    FROM insulin_carb_smoothed_2
                    WHERE %s < rtime and rtime <= %s
                    ORDER BY rtime''',
                 [date_ui.python_datetime_to_mysql_datetime(time_prev),
                  date_ui.python_datetime_to_mysql_datetime(time_now)])
    raw_rows = curs.fetchall()
    logging.debug('first past carbs %s', raw_rows[0])
    logging.debug('last past carbs %s', raw_rows[-1])
    ## We will probably only have a few non-null values. This "or" seems to work.
    vals = [ (row[0] or 0)
             for row in raw_rows ]
    logging.debug('all past carbs %s', vals)
    logging.debug('len past carb values %s', len(vals))
    return vals

# ================================================================

def pm_test():
    '''let time 0 be the time of the first prediction, like pt in the
predictive_model the IAC curve is a 5 hour curve, so 60 steps.

test cases:

1. if there was an input of 1 unit of insulin at time -1 and a basal
rate of 0, we should see the first 20 steps of the IAC play out in our
curve

2. if there was an input of 1 unit of insulin at time -19 and a basal
rate of 0, we should see 20 steps of the IAC play out but not the
first 20, but the second 20.

3. if the past 60 time steps have all had a steady basal rate of 0.01
units and that's continuing, we should see that as every step of the
output.

    '''
    in1 = [ 0 for i in range(60) ]
    in1[-1] = 1
    def isf(x):
        return 50
    out1 = predictive_model_june21(datetime.now(),
                                   bg_now = 100,
                                   bg_prev = 100,
                                   insulin_inputs = in1,
                                   basal_rate_12 = 0.0,
                                   isf_function = isf)

    in2 = [ 0 for i in range(60) ]
    in2[-20] = 1
    out2 = predictive_model_june21(datetime.now(),
                                   bg_now = 100,
                                   bg_prev = 100,
                                   insulin_inputs = in2,
                                   basal_rate_12 = 0.0,
                                   isf_function = isf)

    in3 = [ 0.01 for i in range(60) ]
    out3 = predictive_model_june21(datetime.now(),
                                   bg_now = 100,
                                   bg_prev = 100,
                                   insulin_inputs = in3,
                                   basal_rate_12 = 0.01,
                                   isf_function = isf)

    table = [ list(range(60)), out1, out2, out3 ]
    table = list(zip(*table))
    print(tsv_table_out(table))
    return table

# ================================================================

def get_clean_region(index = None, conn = None):
    '''Return the rtime for a clean region. If index is omitted, choose a random one.
Otherwise, the rtime of the clean region specified by index.'''
    if conn is None:
        conn = dbi.connect()
    curs = dbi.cursor(conn)
    max_region = 726
    if index is None:
        index = random.between(0, num_regions)
    curs.execute('select rtime from clean_regions_5hr limit 1 offset {}'
                 .format(max_region - index))
    return curs.fetchone()[0]

def get_model_inputs(rtime = None, hrs_minus = 5, hrs_plus = 2, conn = None):
    '''Return the the data for the predictive model for a given datetime or the index
for a clean region.'''
    if conn is None:
        conn = dbi.connect()
    rtime = date_ui.to_rtime(rtime)
    curs = dbi.cursor(conn)
    curs.execute('''select rtime,
                           basal_amt_12, total_bolus_volume,
                           carbs, minutes_since_last_meal, carb_code,
                           cgm, bg, coalesce(bg, cgm) as bg2
                    from insulin_carb_smoothed_2
                    where %s <= rtime and rtime <= %s''',
                 [date_ui.python_datetime_to_mysql_datetime(rtime - timedelta(hours=hrs_minus)),
                  date_ui.python_datetime_to_mysql_datetime(rtime + timedelta(hours=hrs_plus))])
    return curs.fetchall()

# See https://note.nkmk.me/en/python-list-transpose/
def transpose(list_of_lists):
    return list(zip(*list_of_lists))

def pad(len, val=''):
    '''return list of this many values'''
    return [ val for i in range(len) ]

def run_hist_pm(datetime=None, index=None, conn=None, debug=False):
    '''run the predictive model on a historical event. Output traces
designed to plotted in Excel.'''
    if conn is None:
        conn = dbi.connect()
    if datetime is None and index is not None:
        # find the specified historical clean region
        datetime = get_clean_region(index)
    if datetime is None:
        raise Exception('Must specify datetime or index')
    datetime = date_ui.to_datetime(datetime)
    # let's get going
    pred_vals, di_vals, dc_vals, di_deltas, dc_deltas, notes = predictive_model_june21(datetime, conn=conn, debug=debug)

    basal_rate_12 = get_basal_rate_12(datetime, conn=conn)

    # Also want to have insulin history. This will be short (60
    # values), but we'll pad it with 20 empty values. Or should it be
    # basal rate? Should be basal rate
    insulin_history = (get_past_insulin_at_time(datetime, conn=conn) +
                       pad(20, val=basal_rate_12))

    # we also want traces of BG before/after. We'll use time=0 as the
    # first timestep of the prediction, so time will go from 5 hours
    # before (5*12=60 steps) to 2 hours after (2*12=24 steps)
    t_zero = datetime
    t_past_60 = datetime - timedelta(hours=5)
    t_plus_20 = datetime + timedelta(hours=2)

    times = [ t*5 for t in range(-60, 20) ]
    past_vals = get_bg_trace(t_past_60, t_zero, conn = conn)
    plus_vals = get_bg_trace(t_zero, t_plus_20, conn = conn)

    past_pred_vals = past_vals + pred_vals
    past_plus_vals = past_vals + plus_vals

    table = [ times,
              past_pred_vals, past_plus_vals, insulin_history,
              pad(60)+di_vals, pad(60)+dc_vals,
              pad(60)+di_deltas, pad(60)+dc_deltas ]
    return transpose(table)

def get_bg_trace(t0, t1, conn = None):
    '''return a trace of BG values from t0 to t1'''
    t0 = date_ui.to_rtime(t0)
    t1 = date_ui.to_rtime(t1)
    if conn is None:
        conn = dbi.connect()
    curs = dbi.cursor(conn)
    curs.execute('''select coalesce(BG, CGM, '') from insulin_carb_smoothed_2
                    where %s <= rtime and rtime <= %s''',
                 [date_ui.python_datetime_to_mysql_datetime(t0),
                  date_ui.python_datetime_to_mysql_datetime(t1)])
    trace = [ row[0] for row in curs.fetchall() ]
    return trace


def tsv_line_out(*args):
    print(('\t'.join(map(str,args))))

def fstr(val):
    if type(val) == type(1.2):
        return format(val, ".4f")
    else:
        return str(val)

def tsv_table_out(table):
    '''Prints a list of lists/tuples as a TSV table; no headers'''
    for row in table:
        print(('\t'.join(map(fstr,row))))


def tsv_dict_table_out(table):
    '''Prints a list of dictionaries as a TSV table; with headers'''
    first = table[0]
    print('\t'.join(map(str,first.keys())))
    for row in table:
        print(('\t'.join(map(str,row.values()))))

def tsv_dict_table_str(table):
    '''converts a list of dictionaries into a TSV string; with headers'''
    first = table[0]
    header_str = ('\t'.join(map(str,first.keys())))
    data_str = [ ('\t'.join(map(str,row.values())))
                 for row in table ]
    return header_str + '\n'.join(data_str)

## ================================================================
## Proposed CAC, based on reverse-engineered CAC from clean rescues,
## divided by carbs (pm_test_5).

CAC = [
    0,
    0.113,
    0.226,
    0.339,
    0.452,
    0.565,
    0.678,
    0.57,
    0.462,
    0.354,
    0.246,
    0.138,
    0.1332413793,
    0.1284827586,
    0.1237241379,
    0.1189655172,
    0.1142068966,
    0.1094482759,
    0.1046896552,
    0.09993103448,
    0.09517241379,
    0.0904137931,
    0.08565517241,
    0.08089655172,
    0.07613793103,
    0.07137931034,
    0.06662068966,
    0.06186206897,
    0.05710344828,
    0.05234482759,
    0.0475862069,
    0.04282758621,
    0.03806896552,
    0.03331034483,
    0.02855172414,
    0.02379310345,
    0.01903448276,
    0.01427586207,
    0.009517241379,
    0.00475862069
]

def normalize(seq):
    total = sum(seq)
    return [ n/total for n in seq ]

# ================================================================
# test values


def get_rescue_carbs(index = None, conn = None):
    '''returns the rtime for one of the 1745 rescue carb events. Index is
1-based, so we can look in a spreadsheet to see the times.'''
    if conn is None:
        conn = dbi.connect()
    if index is None:
        index = random.randint(1, 1745)
        print('index: {}'.format(index))
    # index=1 is the most *recent* not the oldest
    index = 1745-index
    curs = dbi.cursor(conn)
    curs.execute('''select rtime from insulin_carb_smoothed_2
                    where rescue_carbs = 1
                    limit 1 offset {}'''.format(index))
    return curs.fetchone()[0]

def get_all_rescue_carbs(conn = None):
    '''returns the rtime and carbs for all rescue carb events'''
    if conn is None:
        conn = dbi.connect()
    curs = dbi.cursor(conn)
    curs.execute('''select rtime, carbs from insulin_carb_smoothed_2
                    where rescue_carbs = 1
                    order by rtime desc''')
    return tsv_table_out(curs.fetchall())


'''
this is the most recent in anah.clean_regions_5hr
Note that there was a correction at that time (1am),
so we want to take that insulin input into account, so
we want to start our prediction at t+1

'''


f1 = get_past_insulin_at_time
f2 = predictive_model_june21

# but no prev_bg for these times
t1 = '2018-09-13 01:00:00'
t2 = '2018-08-27 01:55:00'
t3 = '2018-08-26 03:05:00'

# okay
t4 = date_ui.to_rtime('2018-08-21 21:00:00')
t5 = date_ui.to_rtime('2018-08-21 02:40:00')
t4_5 = t4 - timedelta(hours=5)

# for Friday 8/6/2021
def pm_test_2():
    tsv_table_out(run_hist_pm(get_clean_region(index=3)))

# set loglevel to 40 to turn off all but ERROR and CRITICAL
# set loglevel to 30 to get WARNING, ERROR and CRITICAL
# set loglevel to 10 to get everything
def pm_test_3(cleans = [], rescues = [0], loglevel=30, conn = None):
    '''Run the predictive model on a bunch of clean regions and a bunch of
rescue carbs regions.'''
    conn = conn if conn else dbi.connect()
    logging.getLogger().setLevel(loglevel)
    if len(rescues) > 0:
        print('================ rescue carb events ================')
    for rescue in rescues:
        rescue_date = get_rescue_carbs(rescue, conn=conn)
        print('================ {} ================'.format(rescue_date))
        table = run_hist_pm(rescue_date, conn=conn)
        tsv_table_out(table)

def pm_test_5(conn = None, loglevel=logging.CRITICAL):
    # compute CAC by looking at clean rescues and dividing by number of carbs
    logging.getLogger().setLevel(loglevel)
    conn = dbi.connect() if conn is None else conn
    rescues = get_clean_rescues(conn=conn, loglevel=loglevel)
    print('================ rescue events ================')
    # tsv_table_out(rescues)
    (_, _, means, smoothed) = usable_cac(conn, loglevel=loglevel)
    print('================ mean standardized trace ================')
    times = list(range(0,365,5))
    print(len(times), len(smoothed))
    table = transpose([times, smoothed])
    tsv_table_out(table)
    print('================ derivative ================')
    next = smoothed[1:]
    diffs = [ pair[1]-pair[0] for pair in zip(smoothed, next) ]
    table = transpose([times, smoothed, diffs])
    tsv_table_out(table)

def pm_test_5b(conn = None, loglevel=logging.DEBUG):
    # compute the predictive model for one of the rescue events, maybe the first
    conn = conn if conn else dbi.connect()
    logging.getLogger().setLevel(loglevel)
    for rescue in [0]:
        rescue_date = get_rescue_carbs(rescue, conn=conn)
        print('================ {} ================'.format(rescue_date))
        table = run_hist_pm(rescue_date, conn=conn)
        print('time\t p BG\t a BG\t In\t DI\t DC\t ')
        tsv_table_out(table)

def what_happened_at(rtime,
                     before=timedelta(hours=3),
                     after=timedelta(hours=3),
                     conn=None):
    conn = conn if conn else dbi.connect()
    curs = dbi.cursor(conn)
    t1 = rtime - before
    t2 = rtime + after
    curs.execute('''select rtime,
                           timestampdiff(MINUTE,%s,rtime) as delta,
                           coalesce(bg, cgm) as abg,
                           total_bolus_volume as insulin,
                           carbs, rescue_carbs,
                           basal_amt_12
                    from insulin_carb_smoothed_2
                    where rtime >= %s and rtime <= %s''',
                 [rtime, t1, t2])
    table = curs.fetchall()
    print('rtime\t delta\t aBG\t insulin\t carbs\t rescue?\t basal12')
    tsv_table_out(table)


def pm_test_6(conn = None, loglevel=logging.DEBUG):
    '''The case we studied in test5, case 0, may be anomalous. Let's look
at another case, and look at whether DI and DC are being computed
correctly. Let's look at event 6, on 2020-10-12 19:30:00

    '''
    conn = conn if conn else dbi.connect()
    logging.getLogger().setLevel(loglevel)
    for rescue in [7]:
        rescue_date = get_rescue_carbs(rescue, conn=conn)
        print('================ {} ================'.format(rescue_date))
        table = run_hist_pm(rescue_date, conn=conn, debug=True)
        print('time\t p BG\t a BG\t In\t DI\t DC\t DDI\t DDC')
        tsv_table_out(table)

def pm_test_7(conn = None, rescue_event = 7, loglevel=logging.DEBUG, isf_function = None):
    '''The case we studied in test5, case 0, may be anomalous. Let's look
at another case, and look at whether DI and DC are being computed
correctly. Let's look at event 6, on 2020-10-12 19:30:00

This uses the new predictive model function.
    '''
    conn = conn if conn else dbi.connect()
    logging.getLogger().setLevel(loglevel)
    rescue_date = get_rescue_carbs(rescue_event, conn=conn)
    print('================ {} ================'.format(rescue_date))
    predictions, rows = predictive_model_sept21(rescue_date, conn=conn,
                                                isf_function = isf_function, debug=True)
    # pull them out of dict in a particular order
    table = [ (row['rtime'], row['delta'], row['abg'], row.get('pred_bg',''),
               row['insulin'], row.get('di',''), row['carbs'], row.get('dc',''),
               row.get('delta_di',''), row.get('delta_dc',''))
              for row in rows ]
    print('atime\t dtime\t actual BG\t pred BG\t Insulin\t DI\t carbs\t DC\t DDI\t DDC')
    tsv_table_out(table)

def pm_test_8(isf, conn = None, rescue_event = 1):
    '''Looking more at rescue_event 1, where the model did pretty well but
P BG > A BG throughout. So, maybe use a lower value of ISF? How much
do we have to bring it down to get a better value?  The ISF value we
used was 16 (time bucket 16). Let's try values below that.

    '''
    isf_function = lambda x: isf
    pm_test_7(conn=conn, rescue_event=rescue_event, isf_function=isf_function)

## ================================================================

# Carb curve from rescue event. Based on Sept 21st predictive model

def carb_curve_from_rescue(time_now,
                            conn = None,
                            debug = False,
                            coef_bg_now = 1, # c0
                            bg_now = None,
                            coef_bg_prev = 0, # c1
                            bg_prev = None,
                            coef_bg_slope = 1, # c2
                            bg_slope = None,
                            coef_effect = 1, # c3
                            past_inputs = None,
                            insulin_inputs = None,
                            basal_rate_12 = None,
                            isf_function = None,
                            iac_curve = None,
                            coef_carbs = 7,
                            carb_curve = None,
                            carb_inputs = None):

    '''Returns a prediction (a trace of BG values) for a length of time
(two hours) from the given time_now. The result is suitable for
plotting along with the actual BG values, if any. Other values have
sensible defaults but can be provided.

Defaults that are None will be read from the database or otherwise
    computed.

This one differs in getting a bunch of past data as dictionaries,
iterating over it to make the predictions, and adding the prediction
to the dictionary. Then converting to a table, for easier analysis.

    '''
    time_now = date_ui.to_datetime(time_now)
    time_now = date_ui.to_rtime(time_now)
    logging.info('predictive model for {}'.format(time_now))
    # computing defaults
    if conn is None:
        conn = dbi.connect()
    curs = dbi.dict_cursor(conn)
    if bg_now is None:
        bg_now = float(get_bg(time_now, conn=conn))
    time_prev = time_now - timedelta(minutes=5)
    if bg_prev is None:
        bg_prev = float(get_bg(time_prev, conn=conn))
    # we may eventually replace this bg_slope with, say, a 30-minute slope
    if bg_slope is None:
        bg_slope = bg_now - bg_prev
    rtime = time_now
    if past_inputs is None:
        # need carbs and insulin to compute DC and DI
        # need rtime and delta time for x-axis
        # need abg (actual bg) for comparison to prediction
        curs.execute('''select rtime,
                        timestampdiff(MINUTE,%s,rtime) as delta,
                           coalesce(bg, cgm) as abg,
                           if(total_bolus_volume is null,basal_amt_12,total_bolus_volume+basal_amt_12) as insulin,
                           if(carbs is null, 0, carbs) as carbs,
                           rescue_carbs,
                           basal_amt_12
                    from insulin_carb_smoothed_2
                    where rtime >= %s and rtime <= %s''',
                 [rtime, rtime-timedelta(hours=5), rtime+timedelta(hours=3)])
        past_inputs = curs.fetchall()
    if basal_rate_12 is None:
        # should get this from past_inputs instead
        basal_rate_12 = get_basal_rate_12(time_now, conn=conn)
    if isf_function is None:
        isf_function = estimated_isf
    logging.debug('initial ISF %s', isf_function(time_now))
    # the percent curve is our IAC
    if iac_curve is None:
        iac_curve = getIAC(conn=conn)
        assert(type(iac_curve) is list and len(iac_curve) == 60)
        # iac_curve.reverse()
    if carb_curve is None:
        carb_curve = normalize(CAC)
        # omit the length check. It'll be 40 and will run out when we
        # do the convolution, but that's okay
        assert(type(carb_curve) is list)
        # carb_curve.reverse()
    # outputs, predictions (bg units) dynamic insulin and dynamic carbs
    predictions = []
    prev_di = 0
    prev_dc = 0
    # New algorithm. Skip the first N rows because we need N past
    # inputs to compute DC and DI. N = max(len(percent_curve), len(carb_curve))
    skip_amt = max(len(iac_curve), len(carb_curve))
    skip_rows = past_inputs[0:skip_amt]
    print('initial insulin inputs',insulin_inputs)
    if carb_inputs is None:
        carbs_in = [ [row['rtime'],row['carbs']]
                      for row in past_inputs
                      if row['carbs'] > 0 ]
        if len(carbs_in) > 1:
            print('multiple carbs_in',carbs_in)
            for i in range(len(carbs_in)-1):
                d1 = carbs_in[i][0]
                d2 = carbs_in[i+1][0]
                print('carbs at',d2, d1, d2-d1)
                if d2 - d1 < timedelta(hours=3):
                    print('two carbs_in less than 3 hours apart',d1, d2, d2-d1)
                    raise Exception('two carbs in less than 3 hours apart')
        carb_inputs = [ row['carbs'] for row in past_inputs ]
    print('initial carb inputs',carb_inputs)
    sum_carbs = sum(carb_inputs)
    rev_carb_curve=[]
    for i in range(skip_amt, len(past_inputs)):
        row = past_inputs[i]
        dynamic_insulin = convolve(past_inputs, i, 'insulin', iac_curve)
        effect = -1 * dynamic_insulin * isf_function(time_now)
        # dynamic_carbs = convolve(past_inputs, i, 'carbs', carb_curve)
        rt = row['rtime']
        logging.debug('RT: %s DT: %s IN: %d BG %.2f DI %.2f Effect %.2f ',
                      rt, row['delta'],
                      row['insulin'],
                      bg_now,
                      dynamic_insulin,
                      effect)
        '''
        bg_next = (coef_bg_now * bg_now +
                   coef_bg_prev * bg_prev +
                   coef_effect * effect +
                   coef_carbs * dynamic_carbs )
        '''
        abg = row['abg']
        other = (coef_bg_now * bg_now +
                 coef_bg_prev * bg_prev +
                 coef_effect * effect)
        carb_curve_t = (abg - other)/sum_carbs
        rev_carb_curve.append(carb_curve_t)
        row['rev_cc'] = carb_curve_t
        row['di'] = dynamic_insulin
        delta_di, prev_di = dynamic_insulin - prev_di, dynamic_insulin
        row['delta_di'] = delta_di
        # Advance now and past
        (bg_now, bg_past, time_now) = (abg, bg_now, time_now+timedelta(minutes=5))
    return rev_carb_curve, past_inputs

def cc_test_1(conn = None, rescue_event = 1, loglevel=logging.DEBUG, isf_function = None):
    '''reverse engineering the carb curve from a rescue event.

This uses the new predictive model function.
    '''
    conn = conn if conn else dbi.connect()
    logging.getLogger().setLevel(loglevel)
    rescue_date = get_rescue_carbs(rescue_event, conn=conn)
    print('================ {} ================'.format(rescue_date))
    carb_curve, rows = carb_curve_from_rescue(rescue_date, conn=conn,
                                              isf_function = isf_function, debug=True)
    # pull them out of dict in a particular order
    table = [ (row['rtime'], row['delta'], row['abg'], row.get('rev_cc',''),
               row['insulin'], row.get('di',''), row['carbs'], row.get('dc',''),
               row.get('delta_di',''), row.get('delta_dc',''))
              for row in rows ]
    print('atime\t dtime\t actual BG\t rev CC\t Insulin\t DI\t carbs\t DC\t DDI\t DDC')
    tsv_table_out(table)


def find_cc_test_1(conn = None):
    possible = []
    for i in range(1,100):
        try:
            cc_test_1(conn, i)
            possible.append(i)
        except:
            pass
    print('possible rescues', possible)


if __name__ == '__main__':
    tab = pm_test_2()
