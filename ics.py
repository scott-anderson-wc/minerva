'''Useful interface functions between md_deploy and the
insulin_carb_smoothed_2 table in the janice database.'''

import sys
import cs304dbi as dbi
from datetime import datetime, timedelta
import date_ui

def debug(*args):
    print('debug', *args)

USER = 'Hugh'

# ================================================================
# Data readout. Helpful for testing and data display

def get_insulin_info(conn, start_time=None, hours=2):
    '''Get insulin info for given time period after given start time
(default to now-hours).  Returns four values, each a list of values:
(1) bolus info, which will be mostly None values; (2)
programmed_basal; (3) basal_amt (this is basal_amt, not basal_amt_12;
(4) extended_bolus.

The second value is currently returned as an empty list; we may add that later at
some point.

    '''
    if start_time is None:
        start_time = datetime.now() - timedelta(hours=hours)
        start_time = date_ui.to_rtime(start_time)
    else:
        # can't trust the user's start_time
        try:
            start_time = date_ui.to_rtime(start_time)
        except ValueError:
            return ([],[],[],[])
    try:
        hours = int(hours)
    except ValueError:
        hours = 2
    end_time = start_time + timedelta(hours=hours)
    desired_len = 12*hours
    curs = dbi.cursor(conn)
    n = curs.execute('''SELECT total_bolus_volume, basal_amt_12, extended_bolus_amt_12
                        FROM insulin_carb_smoothed_2
                        WHERE user = '{}' 
                        AND rtime >= %s and rtime < %s'''.format(USER),
                     [start_time, end_time])
    if n != desired_len:
        debug('in get_insulin_info, wrong number of values: wanted {} got {}'.format(desired_len, n))
    rows = curs.fetchall()
    boluses = [ row[0] for row in rows ]
    prog_basal = []             # fix this someday?
    actual_basal = [ round(row[1]*12,2) for row in rows ]
    extended = [ round(row[2]*12,2) if row[2] is not None else None for row in rows ]
    return (boluses, prog_basal, actual_basal, extended)

def get_cgm_info(conn, start_time=None, hours=2):
    '''Get cgm info for given time period after
given start time (default to now-hours).  Returns a list of values,
suitable for a Plotly trace.

    '''
    if start_time is None:
        start_time = datetime.now() - timedelta(hours=hours)
        start_time = date_ui.to_rtime(start_time)
    else:
        # can't trust the user's start_time
        try:
            start_time = date_ui.to_rtime(start_time)
        except ValueError:
            return []
    try:
        hours = int(hours)
    except ValueError:
        hours = 2
    end_time = start_time + timedelta(hours=hours)
    desired_len = 12*hours
    curs = dbi.cursor(conn)
    n = curs.execute('''SELECT cgm
                        FROM insulin_carb_smoothed_2
                        WHERE user = '{}' 
                        AND rtime >= %s and rtime < %s'''.format(USER),
                     [start_time, end_time])
    if n != desired_len:
        debug('in get_cgm_info, wrong number of values: wanted {} got {}'.format(desired_len, n))
    rows = curs.fetchall()
    cgm_values = [ row[0] for row in rows ]
    return cgm_values


if __name__ == '__main__':
    conn = dbi.connect()
    boluses, prog_basal, actual_basal, extended_boluses = get_insulin_info(conn)
    print('boluses:')
    print(boluses)
    print('programmed basal')
    print(prog_basal)
    print('actual basal')
    print(actual_basal)
    print('extended boluses')
    print(extended_boluses)
    cgm = get_cgm_info(conn)
    print('cgm')
    print(cgm)
    
