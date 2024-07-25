'''Useful interface functions between md_deploy and the
insulin_carb_smoothed_2 table in the janice database.'''

import sys
import cs304dbi as dbi
from datetime import datetime, timedelta
import date_ui

def debug(*args):
    print('debug', *args)

USER = 'Hugh'
USER_ID = 7
DEFAULT_HOURS = 6

# ================================================================
# Data readout. Helpful for testing and data display

def get_insulin_info(conn, start_time=None, hours=DEFAULT_HOURS):
    '''Get insulin info for given time period after given start time
(default to now-hours).  Returns these values, each a list of numeric values or None:
    (1) bolus info, which will be mostly None values;
    (2) programmed_basal;
    (3) basal_amt (this is basal_amt, not basal_amt_12;
    (4) extended_bolus
    (5) dynamic_insulin

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
    n = curs.execute('''SELECT total_bolus_volume, basal_amt_12, extended_bolus_amt_12, dynamic_insulin
                        FROM insulin_carb_smoothed_2
                        WHERE user = '{}' 
                        AND rtime >= %s and rtime < %s'''.format(USER),
                     [start_time, end_time])
    if n != desired_len:
        # this can happen when there is no updated data from the
        # pump. Since that's not uncommon, let's skip the debug statement.
        # debug('in get_insulin_info, wrong number of values: wanted {} got {}'.format(desired_len, n))
        pass
    rows = curs.fetchall()
    boluses = [ row[0] for row in rows ]
    di_values = [ row[3] for row in rows ]
    prog_basal = []             # fix this someday?
    # for cosmetic reasons, multiply by 12 and round to 2 digits
    def round2x12(x):
        return round(x*12,2) if x is not None else None
    actual_basal = [ round2x12(row[1]) for row in rows ]
    extended = [ round2x12(row[2])  for row in rows ]
    return (boluses, prog_basal, actual_basal, extended, di_values)

def get_last_autoapp_update(conn):
    curs = dbi.cursor(conn)
    curs.execute('SELECT date FROM autoapp.dana_history_timestamp WHERE user_id = %s', [USER_ID])
    last_update = curs.fetchone()[0]
    return last_update

def get_cgm_info(conn, start_time=None, hours=DEFAULT_HOURS, debug_on=False):
    '''Get cgm info for given time period after
given start time (default to now-hours).  Returns a list of values,
suitable for a Plotly trace.

    '''
    # convert hours first, since that's used in converting start_time
    try:
        hours = int(hours)
    except ValueError:
        hours = 2
    # default start_time is now - hours
    if start_time is None:
        start_time = datetime.now() - timedelta(hours=hours)
        start_time = date_ui.to_rtime(start_time)
        if debug_on:
            debug('start_time:', start_time)
    else:
        # can't trust the user's start_time to parse correctly
        try:
            start_time = date_ui.to_rtime(start_time)
            if debug_on:
                debug('start_time:', start_time)
        except ValueError:
            return []
    end_time = start_time + timedelta(hours=hours)
    if debug_on:
        debug('end_time:', end_time)
    desired_len = 12*hours
    curs = dbi.cursor(conn)
    n = curs.execute('''SELECT cgm,rtime
                        FROM insulin_carb_smoothed_2
                        WHERE user = '{}' 
                        AND rtime >= %s and rtime < %s
                        ORDER BY rtime'''.format(USER),
                     [start_time, end_time])
    rows = curs.fetchall()
    if debug_on and n != desired_len:
        # we can get too few if the last value of realtime_cgm hasn't yet migrated.
        # that seems common enough that I'm going to skip the debug statements
        debug('in get_cgm_info({},{}), wrong number of values: wanted {} got {}'
              .format(start_time, hours, desired_len, n))
        debug(rows[0])
        debug(rows[-1])
        pass
    if debug_on:
        for row in rows:
            debug(str(row[0]),date_ui.dstr(row[1]))
    cgm_values = [ row[0] for row in rows ]
    return cgm_values


if __name__ == '__main__':
    conn = dbi.connect()
    boluses, prog_basal, actual_basal, extended_boluses, di_values = get_insulin_info(conn)
    print('boluses:')
    print(boluses)
    print('programmed basal')
    print(prog_basal)
    print('actual basal')
    print(actual_basal)
    print('extended boluses')
    print(extended_boluses)
    print('dynamic_insulin')
    print(di_values)
    cgm = get_cgm_info(conn)
    print('cgm')
    print(cgm)
    print('last autoapp update', get_last_autoapp_update(conn))
    
