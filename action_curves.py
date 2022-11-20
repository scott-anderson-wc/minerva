'''We use several action curves, all of which show how past inputs
manifest in the present:

The insulin action curve (IAC) shows how past insulin (basal and
bolus) affect the current moment. In particular, the curve values are
multiplied by the past inputs saying what percent of that input is
active right now. That's then multiplied by ISF (insulin sensitivity
factor) to calculate how much the BG goes down as a result of the past
insulin.

the carb action curve (CAC) shows how past carbs (brunch, dinner,
rescue) affect the current moment. The values are multiplied by the
past inputs saying what percent of that input hits the bloodstream
(and thereby increases the BG).

There are three CAC curves, roughly in increasing order of their peak

* rescue (fast carbs, reaches the peak soonest)
* breakfast and lunch, which I'll call brunch
* dinner

The curves are represented just as a list of numbers summing to 100
percent.

For the sake of clarity, these curves will be put in a global
dictionary indexed by the meal. The curves are not necessarily the
same length. The values below are placeholders, not real.

action_curves = {
    'rescue' : [0.3, 0.4, 0.2, 0.1],
    'brunch' : [0.2, 0.3, 0.4, 0.05, 0.05],
    'dinner' : [0.1, 0.2, 0.3, 0.2, 0.1, 0.05, 0.05]
    'insulin' : [0.04, 0.08, ... 0.02, 0.01 ]
}

For ease of computation, it turns out to be convenient to have the
curves in reverse order. Rather than continually reversing the list or
worrying about whether we've already reversed it, we will store the
reversed lists as well:

action_curves_reversed = {
    'rescue' : [0.1, 0.2, 0.4, 0.3],
    'brunch' : [0.05, 0.05, 0.4, 0.3, 0.2],
    'dinner' : [0.05, 0.05, 0.1, 0.2, 0.3, 0.2, 0.1]
    'insulin' : [0.01, 0.02, ... 0.08, 0.04 ]
}

We have several ways of doing the action curves. In the most general
case, we can read an list of values from a file (one value per line),
as exported by a spreadsheet. One specific case is to use the Beta
curve model:

t**a (1-t)**b / sum

the two parameters, a and b, determine the curve. The curve doesn't
sum to 100 percent, so we calculate that sum and divide through.

We should be able to read the parameter values from a file or from a
database table; that will allow us to update the parameters using some
kind of adjustment or machine learning (ML). That's still TBD.

In the past, I created a table, insulin_action_curve, that holds our
history of insulin action curves. We can read the latest as a JSON
value, and cache it. I now see that this table should become more
general:

create table action_curves(
    uid int,
    kind enum('brunch','dinner','rescue','insulin'),
    curve_date timestamp,
    curve varchar(1000) comment 'the values on the curve as JSON. worst case: 6 chars/value * 12/hour * 6 hours = 432',
    notes text,
    primary key (uid, kind, curve_date)
);

This is written in sql/create-action-curves.sql

Data representation


TODO:

* add a endpoint to the md_deploy that plots the various action curves

October 14, 2022
Scott D. Anderson

'''

import math
import csv
import json
import logging
import cs304dbi as dbi

HUGH_UID = 7

# this is the maximum length of the JSON representation of the curve
MAX_CURVE_JSON_LENGTH = 1000

def debugging():
    logging.basicConfig(level=logging.DEBUG)

## ================================================================
## Data Representation

'''Data representation is always a hassle. Internally, we should do
computations using floating point. The curves should sum to 1.0 (100
percent). Externally, we can't ensure that the printed presentation of
all those floats will be reasonably compact, and we won't have ugly
stuff like 0.0340000001. So, we'll round things to integers, summing
to 10_000.  (We can choose any other value, but that gives us 4 digits
of precision, which seems pretty good.)

These two functions compute the sequence we want for various purposes.
'''

def sum_hundred_percent(seq):
    '''Return a sequence of floats summing to 1.0 or as close as floating
point will get. We check that it is within 1 part in 10_000.
    '''
    if len(seq) == 0:
        raise ValueError('seq is empty')
    total = float(sum(seq))
    if abs(total - 1.0) <= 1.0/float(10_000):
        # close enough
        return seq
    else:
        float_seq = [ n/total for n in seq ]
        float_sum = sum(float_seq)
        if abs(float_sum - 1.0) <= 1.0/float(100_000):
            # close enough
            return float_seq
        else:
            raise Exception('Could not normalize to 1.0')

## Note: this function is simple but not as good as it could be. In
## particular, for our current IAC, the integer sequence sums to
## 100_010, which fails our original criteria of 99_995 to
## 100_005. The sequence is pretty good, but by ill luck, a lot of the
## values are like 408.96 and such, so that ten of them round UP. So,
## we really need to pick a few of them and round them DOWN, so that
## we sum to something closer to 100_000. *sigh*

## Instead, I loosened the criteria, so it's more forgiving

## And, of course, I need to change the name.

def sum_ten_thousand(seq):
    '''Return a sequence of integers summing to 100,000 plus or minus
5. This will be compact to store (5 digits each) and no issues of
roundoff and such.
    '''
    total = sum(seq)
    def okay(val):
        # return 99_995 <= val <= 100_005
        return 99_990 <= val <= 100_010

    if okay(total):
        return seq
    else:
        int_seq = [ round(100_000*float(n)/float(total))
                    for n in seq ]
        int_total = sum(int_seq)
        if okay(int_total):
            return int_seq
        else:
            raise Exception('Could not normalize this sequence to 100_000')

## ================================================================
## File System I/O

def read_curve_from_csv(filename, kind, skip_lines=0, uid=7):
    '''Reads an arbitrary curve from the given CSV file and returns
it. The format is just a single column, easy to export from any
spreadsheet. Returns it in internal format, summing to 100
percent. You can skip some number of lines in the file, say if there's
a header line.

    '''
    # we don't need to worry about delimiters, because there's only one column
    curve = []
    with open(filename) as csvfile:
        for row in csv.reader(csvfile):
            if skip_lines > 0:
                skip_lines -= 1
                continue
            curve.append(row[0])
    return sum_hundred_percent(curve)

def write_curve_to_csv(curve_values, filename, kind, skip_lines=0, uid=7):
    '''Writes an arbitrary curve to the given CSV file. Uses an external
format, integers summing to ten thousand.'''
    # we don't need to worry about delimiters, because there's only one column
    int_seq = sum_ten_thousand(curve_values)
    with open(filename, 'w') as csvfile:
        writer = csv.writer(csvfile)
        for val in int_seq:
            writer.writerow(val)

## ================================================================
## Database I/O

def insert_action_curve(conn, uid, kind, curve_values, notes):
    '''Take a set of curve values and store it in the database. The stored
representation is as integers summing about 10K, making it compact
with relatively little roundoff error.'''
    if conn is None:
        conn = dbi.connect()
    curs = dbi.cursor(conn)
    norm = sum_ten_thousand(curve_values)
    data = json.dumps(norm)
    if len(data) > MAX_CURVE_JSON_LENGTH:
        raise Exception('json data too long')
    curs.execute('''INSERT INTO action_curves(uid, kind, curve_date, curve, notes)
                    VALUES(%s, %s, now(), %s, %s)''',
                 [uid, kind, data, notes])
    conn.commit()

def get_action_curve(conn, uid, kind):
    '''Returns the latestest curve of the given kind. Second value is any
notes. Reads from the database, not from the filesystem. Raises an
exception if there's no such curve in the database.

    '''
    if conn is None:
        conn = dbi.connect()
    curs = dbi.cursor(conn)
    curs.execute('''SELECT max(curve_date) FROM action_curves
                    WHERE uid = %s and kind = %s''',
                 [uid, kind])
    row = curs.fetchone()
    max_date = row[0]
    if max_date is None:
        raise Exception(f'No {kind} action curve is in the database')
    logging.info(f'latest {kind} curve is from {max_date}')
    curs.execute('''SELECT curve, notes FROM action_curves
                    WHERE uid = %s and kind = %s and curve_date = %s''',
                 [uid, kind, max_date])
    (curve, notes) = curs.fetchone()
    curve_values = json.loads(curve)
    norm = sum_hundred_percent(curve_values)
    logging.info(f'latest {kind} curve has {len(curve_values)} values')
    return norm

## ================================================================
## Beta Curves

def compute_beta_curve(param_a, param_b, num_values):
    '''Compute num_values for a beta curve with the given parameters.'''
    t_values = [ n/float(num_values) for n in range(num_values) ]
    y_values = [ math.pow(t,param_a)*math.pow(1-t,param_b)
                 for t in t_values ]
    return sum_hundred_percent(y_values)

## ================================================================
## Stats and reporting

def curve_stats(curve):
    '''return the peak, peak_time and duration of a curve'''
    peak_val = max(curve)
    # each curve step is 5 minutes, so peak time is 5*index
    peak_time = curve.index(peak_val) * 5
    duration = len(curve) * 5
    return (peak_val, peak_time, duration)

def curve_stats_as_str(curve, kind):
    '''describe curve as a string, suitable for printing or logging'''
    peak_val, peak_time, duration = curve_stats(curve)
    return f'The {kind} curve peaks at {peak_time} and lasts for {duration}'

## ================================================================
## Putting it together. These functions are run on an ad-hoc basis
## when we have a revised file for one or another curve, like

'''
python
>>> import action_curves as ac
>>> ac.load_table_from_file(None, 'my-new-dinner-curve.csv', 'dinner')
>>> quit()
'''

def load_table_from_file(conn, csv_filename, kind, skip_lines=0):
    '''load an action curve from a CSV file. Actually, it's just one
column of data, so the delimiter is irrelevant. Assumes the file is
just data values; without a header, but you can skip some number of
lines using the keyword argument. This saves the action curve in the
database table.

    '''
    if conn is None:
        conn = dbi.connect()
    curve = read_curve_from_csv(csv_filename, kind, skip_lines)
    insert_action_curve(conn, HUGH_UID, kind, curve, '')

def load_all_tables():
    '''If we have global constants defined that have the various curves,
this loads all of them. Probably not useful; we will probably adjust
curves individually and on an ad hoc basis.'''
    conn = dbi.connect()
    load_table_from_file(conn, FILENAME_FOR_RESCUE_CARB_CURVE, 'rescue')
    load_table_from_file(conn, FILENAME_FOR_BRUNCH_CARB_CURVE, 'brunch')
    load_table_from_file(conn, FILENAME_FOR_DINNER_CARB_CURVE, 'dinner')
    load_table_from_file(conn, FILENAME_FOR_INSULIN_ACTION_CURVE, 'insulin')

def ad_hoc_carb_curves():
    '''A few "from thin air" carb curves for now. 10/21/2022. See
https://docs.google.com/spreadsheets/d/1bVvAMjRVeu15b2roQ4kw_Ya7pKK2ioSdd5a_hN_jDbM/edit#gid=67539943
Run this as:
python
>>> import action_curves as ac
>>> ac.ad_hoc_carb_curves()
>>> quit()
'''
    rescue = compute_beta_curve(2, 6, 24) # two hour curve
    brunch = compute_beta_curve(2, 2, 36) # three hour curve
    dinner = compute_beta_curve(2, 6, 72) # six hour curve
    conn = dbi.connect()
    insert_action_curve(conn, HUGH_UID, 'rescue', rescue, 'ad hoc 10/21/2022, a=2, b=6, d=24')
    insert_action_curve(conn, HUGH_UID, 'brunch', brunch, 'ad hoc 10/21/2022, a=2, b=2, d=36')
    insert_action_curve(conn, HUGH_UID, 'dinner', dinner, 'ad hoc 10/21/2022, a=2, b=6, d=72')

def copy_iac():
    '''one-time only function to copy the IAC from the old
insulin_action_curve table to the new action_curve table, changing
format.'''
    import predictive_model_june21 as pm
    conn = dbi.connect()
    iac = pm.getIAC(conn)
    # the IAC we had been using are all 0.wxyz values and it sums to 1.0000999999999998 which
    # can't meet our normalization criteria, so we do a custom normalization first
    iac_sum = sum(iac)
    iac_norm = [ x/iac_sum for x in iac ]
    iac_sum_after = sum(iac_norm)
    print(f'iac sum was {iac_sum} but is now {iac_sum_after}')
    insert_action_curve(conn, HUGH_UID, 'insulin', iac_norm, 'copied IAC from old table on 10/21/2022')


## This function should be run once when we want to make predictions,
## say using the predictive_model_sept21(), function. Because it
## caches the data, it's safe to run it more than once.

action_curves = None
action_curves_reversed = None

def cache_action_curves(conn):
    '''Reads 4 action curves from the database table and returns two
dictionaries: action_curves and action_curves_reversed. It also caches
the results, so you can call this function again at zero cost. It
should be read before running the predictive model.

    '''
    global action_curves, action_curves_reversed
    if action_curves is not None:
        return action_curves, action_curves_reversed
    if conn is None:
        conn = dbi.connect()
    rescue_curve = get_action_curve(conn, HUGH_UID, 'rescue')
    brunch_curve = get_action_curve(conn, HUGH_UID, 'brunch')
    dinner_curve = get_action_curve(conn, HUGH_UID, 'dinner')
    insulin_curve = get_action_curve(conn, HUGH_UID, 'insulin')
    logging.info(curve_stats_as_str(rescue_curve, 'rescue'))
    logging.info(curve_stats_as_str(brunch_curve, 'brunch'))
    logging.info(curve_stats_as_str(dinner_curve, 'dinner'))
    logging.info(curve_stats_as_str(insulin_curve, 'insulin'))
    action_curves = {'rescue': rescue_curve,
                     'brunch': brunch_curve,
                     'dinner': dinner_curve,
                     'insulin': insulin_curve}
    action_curves_reversed = {'rescue': list(reversed(rescue_curve)), # Mileva todo
                              'brunch': list(reversed(brunch_curve)),
                              'dinner': list(reversed(dinner_curve)),
                              'insulin': list(reversed(insulin_curve))}
    return action_curves, action_curves_reversed
