'''Migrates Hugh's records from the autoapp database to the insulin_carb_smoothed_2 table in the janice database'''

import os                       # for path.join
import sys
import math                     # for floor
import collections              # for deque
import cs304dbi as dbi
from datetime import datetime, timedelta
import date_ui
import logging
from migrate_basal_rate import migrate_basal_12

# Configuration Constants

# probably should have different logs for production vs development
LOG_DIR = '/home/hugh9/autoapp_to_ics2_logs/'

mysql_fmt = '%Y-%m-%d %H:%M:%S'

# this is the table we'll update. Change to janice.insulin_carb_smoothed_2 when we're ready
# TABLE = 'janice.mileva_test'
TABLE = 'janice.insulin_carb_smoothed_2'
USER = 'Hugh'
USER_ID = 7

def debugging():
    '''Run this in the Python REPL to turn on debug logging. The default is just error'''
    logging.basicConfig(level=logging.DEBUG)

## ----------------------------- Setup functions ----------------------------------------

def create_test_tables(conn):
    ''' Create mileva_test table (used to test the migration process during development).'''
    curs = conn.cursor()

    curs.execute('''drop table if exists janice.mileva_test;''')
    curs.execute('''create table janice.mileva_test like insulin_carb_smoothed_2;''')
    conn.commit()
    # copy data from ICS for 2021
    curs.execute('''insert into janice.mileva_test
                    (select * from insulin_carb_smoothed_2 where year(rtime) = 2021)''')
    conn.commit()

def import_functions(conn):
    '''Import necessary mysql functions in the janice database'''

    curs = conn.cursor()

    ## date5f function
    # Import date5f function
    curs.execute('''drop function if exists janice.date5f;''')
    curs.execute('''create function janice.date5f( d datetime )
                    returns  datetime  deterministic
                    return cast(concat(date(d), ' ', hour(d), ':', 5*floor(minute(d)/5))
                        as datetime);''')
    conn.commit()
    ## Test date5f function
    # curs.execute('''select janice.date5f(date) from janice.insulin_carb limit 5;''')
    # results = curs.fetchall()
    # print(results)

## ================================================================
## Fill Forward

def fill_forward_between(conn, start_time, end_time):
    '''The migration functions will assume that the ICS2 table has all the
necessary rows, so we can do the updates using the SQL UPDATE
statement rather than mess with REPLACE or INSERT ON DUPLICATE
KEY. This function establishes that precondition. All the functions
below can call this function first. It's idempotent, so calling it
unnecessarily is fine. Soon, we'll set this up as to be invoked via
CRON.  The function returns the rtime where it started. However, other
migration functions should start from autoapp.last_update.date. See
get_migration_time().

    I considered doing minutes_since_last_meal and
    minutes_since_last_bolus here, but if there's an outage and we end
    up filling a bunch of rows where there might be meals or boluses,
    then this becomes complicated, and I would rather keep this
    function simple and robust.

    '''
    start_time = date_ui.to_rtime(start_time)
    end_time = date_ui.to_rtime(end_time)
    curs = conn.cursor()
    logging.debug(f'fill_forward_between: inserting rows into {TABLE} from {start_time} to {end_time}')
    # this part needs to be idempotent, particularly when we are testing, so
    # I added the ON DUPLICATE KEY no-op
    insert = f'''INSERT INTO {TABLE}(rtime, user)
                 VALUES(%s, '{USER}')
                 ON DUPLICATE KEY UPDATE user=user; '''
    rtime = start_time
    while rtime < end_time:
        curs.execute(insert, [rtime])
        rtime += timedelta(minutes=5)
    conn.commit()

## ----------------------------- Migration ----------------------------------------

    
def print_rows(rows):
    keys = rows[0].keys()
    print('\t'.join(keys))
    for row in rows:
        # can I just use values?
        row_list = [ str(row[k]) for k in keys ]
        print('\t'.join(row_list))

# ================================================================

def bolus_import_s(conn, start_time, end_time, debugp=False):
    '''An S entry means just a simple bolus. But what does a non-zero
duration mean? See #57 among others.'''
    curs = conn.cursor()

    # Note, there are 13 rows where the date in the
    # bolus table equals the date in the basal_hour table. Are those
    # incompatible?

    # Note that because the rows should now exist, we have to use the
    # on duplicate key trick, because replace will *delete* any
    # existing row and replace it. We don't want that. We want to
    # update it if it's already there, and it will be. There may be a
    # more efficient way to do this, but it works. So, in practice,
    # this should not insert any rows, but update existing rows, and
    # it should be idempotent.

    # Now that we have relevance_lag, this should capture S boluses in
    # the recent past. The ON DUPLICATE KEY code should make it
    # idempotent.
    nr = curs.execute(f'''insert into {TABLE}( rtime, bolus_type, total_bolus_volume)
                         select
                            janice.date5f(date),
                            type,
                            if(value='', NULL, value)
                        from autoapp.bolus
                        where user_id = 7 and type = 'S' and date >= %s and date <= %s
                        ON DUPLICATE KEY UPDATE 
                            bolus_type = values(bolus_type),
                            total_bolus_volume = values(total_bolus_volume)''',
                      [start_time, end_time])
    if not debugp:
        conn.commit()
    return nr

def bolus_import_s_test(conn, start_time, end_time):
    start_time = date_ui.to_rtime(start_time)
    end_time = date_ui.to_rtime(end_time)
    curs = conn.cursor()
    nr = curs.execute('''select janice.date5f(date),type,if(value='', NULL, value)
                         from autoapp.bolus
                         where user_id = 7 and type = 'S' and date >= %s and date <= %s''',
                 [start_time, end_time])
    print(f'{nr} S boluses between {start_time} and {end_time}')
    print_rows(curs.fetchall())
    nr = bolus_import_s(conn, start_rtime, debugp=True)
    print('result: {} rows modified'.format(nr))
    nr = curs.execute(f'''select rtime, bolus_type, total_bolus_volume
                         from {TABLE}
                         where bolus_type = 'S' and rtime >= %s and rtime < %s''',
                      [start_time, end_time])
    print(f'imported {nr} S boluses between {start_time} and {end_time}')
    print_rows(curs.fetchall())
    
def bolus_import_ds(conn, start_time, end_time, debugp=False):
    '''A DS entry is, I think, the same as an S entry, but maybe is paired
    with a DE entry?  '''
    # DS events. Treating them just like S, for now.
    curs = conn.cursor()
    # Again, the ON DUPLICATE KEY trick should make this idempotent
    n = curs.execute(f'''insert into {TABLE}( rtime, bolus_type, total_bolus_volume)
                    select 
                        janice.date5f(date),
                        'DS',
                        if(value='', NULL, value)
                    from autoapp.bolus
                    where user_id = 7 and type = 'DS' and date >= %s and date <= %s
                    ON DUPLICATE KEY UPDATE 
                        bolus_type = values(bolus_type),
                        total_bolus_volume = values(total_bolus_volume)''',
                     [start_time, end_time])
    logging.debug('updated with {} DS events from bolus table'.format(n))
    if not debugp:
        conn.commit()

def bolus_import_ds_test(conn, start_time, end_time):
    start_time = date_ui.to_rtime(start_time)
    end_time = date_ui.to_rtime(start_time)
    curs = conn.cursor()
    nr = curs.execute('''select janice.date5f(date),type,if(value='', NULL, value)
                         from autoapp.bolus
                         where user_id = 7 and type = 'DS' and date >= %s and date <= %s''',
                 [start_time, end_time])
    print(f'{nr} DS boluses between {start_time} and {end_time}')
    print_rows(curs.fetchall())
    nr = bolus_import_ds(conn, start_time, end_time, debugp=True)
    print('result: {} rows modified'.format(nr))
    nr = curs.execute(f'''select rtime, bolus_type, total_bolus_volume
                         from {TABLE}
                         where bolus_type = 'DS' and rtime >= %s and rtime <= %s'''
                      [start_rtime])
    print(f'{nr} DS boluses between {start_time} and {end_time}')
    print_rows(curs.fetchall())

def approx_equal(x, y, maxRelDiff = 0.0001):
    '''see https://randomascii.wordpress.com/2012/02/25/comparing-floating-point-numbers-2012-edition/
true if the numbers are within maxRelDiff of each other, default 0.01%'''
    diff = abs(x-y)
    x = abs(x)
    y = abs(y)
    larger = x if x > y else y
    return diff <= larger * maxRelDiff

    
# ================================================================

def extended_bolus_import(conn, start_time, end_time, debugp=False):
    '''because extended boluses aren't recorded in the bolus table until
they complete, we have to use a different approach. We'll look at the
extended_bolus_state table, and compute the start time of the extended
bolus from the date - progress_minutes and the duration from minutes.'''
    curs = dbi.cursor(conn)
    n = curs.execute(f'''SELECT * 
                        FROM (SELECT date  
                                     - interval progress_minutes minute as e_start,
                                    date, absolute_rate, minutes, progress_minutes
                              FROM autoapp.extended_bolus_state
                              WHERE user_id = {USER_ID}) as tmp
                        WHERE e_start > %s and e_start < %s''',
                     [start_time, end_time])
    logging.debug(f'updating with {n} extended bolus reports between {start_time} and {end_time}')
    last_start_time = None
    dst = conn.cursor()
    for row in curs.fetchall():
        # is it volume or rate?
        e_start, date, volume, duration, progress = row
        e_start = date_ui.to_rtime_round(e_start)
        logging.debug('start {} vol {} dur {} progress {}'.format(e_start,volume,duration,progress))
        # last_start_time might be None or an earlier, different extended bolus
        if last_start_time == e_start:
            # we've done this one
            logging.debug('skipping {}'.format(e_start))
            continue
        last_start_time = e_start
        end_rtime = date_ui.to_rtime(e_start + timedelta(minutes=duration))
        extended_bolus_amt_12 = volume / math.floor(duration/5)
        # we'll drip into the row with the start time (<=), but not the row with the end time (<)
        # Because this is an update, it should be idempotent
        dst.execute('''UPDATE {} SET extended_bolus_amt_12 = %s 
                       WHERE user='{}' AND %s <= rtime and rtime < %s'''.format(TABLE,USER),
                      [extended_bolus_amt_12, e_start, end_rtime])
    conn.commit()

def extended_bolus_import_test(conn, start_time, end_time):
    start_time = date_ui.to_rtime(start_time)
    end_time = date_ui.to_rtime(end_time)
    curs = conn.cursor()
    nr = curs.execute('''select janice.date5f(date),type,if(value='', NULL, value), duration
                         from autoapp.bolus
                         where user_id = 7 and type in ('DE','E')
                           AND date >= %s and date <= %s ''',
                 [start_time, end_time])
    print(f'{nr} extended boluses between {start_time} and {end_time}')
    print_rows(curs.fetchall())
    # before updating the destination TABLE, let's null out the extended_bolus_amt_12
    curs.execute(f'update {TABLE} set extended_bolus_amt_12 = null where rtime >= %s and rtime <= %s',
                 [start_time, end_time])
    conn.commit()
    nr = extended_bolus_import(conn, start_time, end_time, debugp=True)
    print('result: {} rows modified'.format(nr))
    # find sum of these DE drips
    curs.execute('''select sum(value) from autoapp.bolus 
                    where user_id = 7 and type in ('DE','E') and date >= %s and date <= %s''',
                 [start_time, end_time])
    row = curs.fetchone()
    before_sum = row[0]
    print('those all sum to {}'.format(before_sum))
    # because the boluses extend over time, I'm going to get every row, so
    # we can see when they start/stop
    nr = curs.execute(f'''select rtime, bolus_type, extended_bolus_amt_12
                         from {TABLE}
                         where rtime >= %s and rtime <= %s
                         AND extended_bolus_amt_12 is not null''',
                      [start_time, end_time])
    print(f'{nr} extended boluses between {start_time} and {end_time}')
    print_rows(curs.fetchall())
    # let's also print the sum. Unfortunately, this sum will also include E boluses. What to do....
    # for debugging, we'll go back and set all the extended_bolus_amt_12 to null at the top of this
    curs.execute(f'select sum(extended_bolus_amt_12) from {TABLE} where rtime >= %s and rtime <= %s',
                 [start_time, end_time])
    row = curs.fetchone()
    after_sum = row[0]
    print('those all sum to {}'.format(after_sum))
    # floating point equality: less than 0.01%
    print('are the sums approximately equal? {}'.format(approx_equal(before_sum, after_sum)))


# ================================================================


def bolus_import(conn, start_time, end_time, debugp=False):

    '''Migrates the bolus table from autoapp. 

An DE entry is when the extended dose (changed basal) ends. Sometimes, it's paired with a DS entry.
  For example:
|     1062 |       7 | 2021-12-27 21:44:00 | DS   | 1.4000000000000001 |        0 | 2021-12-27 21:56:26 |
|     1065 |       7 | 2021-12-27 23:44:00 | DE   | 1.4000000000000001 |      120 | 2021-12-27 23:56:24 |

Why are bolus ids going up when date goes down?
Why are some bolus ids missing?

    '''
    bolus_import_s(conn, start_time, end_time, debugp=debugp)
    bolus_import_ds(conn, start_time, end_time, debugp=debugp)
    extended_bolus_import(conn, start_time, end_time, debugp=debugp)
    # Added this to fix any carb_codes that were incorrect because the
    # bolus hadn't yet been recorded.
    update_carb_codes(conn, start_time, end_time, debugp=debugp)

## ================================================================
## Carb import needs to also compute the carb code.

# meal_name is also defined in iob2.py
from dynamic_insulin import meal_name

MEAL_INSULIN_TIME_INTERVAL = 30

def carbohydrate_import(conn, start_rtime, end_rtime=date_ui.to_rtime(datetime.now()), debugp=False):
    '''Gets all the recent carbs in autoapp (all carbs after
start_time), and for each, searches if there has been recent
boluses. If so, these are a meal and we compute the meal_name
(carb_code) and store that. Otherwise, these are rescue carbs and we
store that.  Also resets the counter for minutes_since_last_meal to
zero unless the carbs are rescue carbs.

Update June 2024: this imports from start_time to end_rtime,
with the end defaulting to NOW.

Note that this only affects rows with carbs. All other rows are
ignored, so carbs, carb_code and minutes_since_last_meal will all be
null. The latter is a problem that is fixed by a different function
(update_minutes_since_last meal).

    '''
    curs = conn.cursor()
    nrows = curs.execute('''select janice.date5f(date) as rtime, value as carbs
                            from autoapp.carbohydrate
                            where date >= %s and date <= %s''',
                         [start_rtime, end_rtime])
    logging.debug(f'found {nrows} carbs to migrate between {start_rtime} and {end_rtime}')
    update = conn.cursor()
    for row in curs.fetchall():
        (rtime, carbs) = row
        if matching_insulin_bolus(conn, rtime):
            carb_code = meal_name(rtime)
        else:
            carb_code = 'rescue'
        logging.debug(f'{carbs} carbs at {str(rtime)} is {carb_code}')
        # set minutes since last meal to zero iff carb_code is not rescue otherwise keep it the same
        update.execute(f'''update {TABLE} 
                           set carbs = %s, carb_code = %s,
                           minutes_since_last_meal = if(%s='rescue',minutes_since_last_meal,0)
                           where rtime = %s''',
                       [carbs, carb_code, carb_code, rtime])
        if not debugp:
            conn.commit()

def matching_insulin_bolus(conn, carb_rtime, time_interval=MEAL_INSULIN_TIME_INTERVAL, debugp=False):
    '''Looks back (and forward) time_interval minutes from carb_rtime for
any boluses. Returns true if any.
    '''
    curs = dbi.dict_cursor(conn)
    carb_rtime = date_ui.to_rtime(carb_rtime)
    time0 = carb_rtime - timedelta(minutes=time_interval)
    time1 = carb_rtime + timedelta(minutes=time_interval)
    recent = curs.execute(f'''select rtime from {TABLE} 
                              where %s < rtime and rtime < %s 
                              and total_bolus_volume is not null''',
                          [time0, time1])
    logging.debug(f'number of matching boluses in {TABLE} around {carb_rtime}: {recent}')
    return recent > 0


def update_carb_codes(conn, rtime0, rtime1, debugp=True):
    '''updates the carb codes for the given time range. Could be a long
range if we are fixing past mistakes, or recent past because we just
migrated a bolus.'''
    if conn is None:
        conn = dbi.connect()
    curs = dbi.cursor(conn)
    rtime0 = date_ui.to_rtime(rtime0)
    rtime1 = date_ui.to_rtime(rtime1)
    logging.debug(f'searching for carbs from {rtime0} to {rtime1}')
    nrows = curs.execute('''select rtime, carbs
                            from janice.insulin_carb_smoothed_2
                            where carbs > 0 
                            and (carb_code is null or
                                 carb_code not in ('before6', 'breakfast', 'lunch', 'snack', 'dinner', 'after9', 'rescue'))
                            and %s <= rtime and rtime <= %s''',
                         [rtime0, rtime1])
    logging.debug(f'found {nrows} carbs to update')
    for row in curs.fetchall():
        (rtime, carbs) = row
        if matching_insulin_bolus(conn, rtime):
            carb_code = meal_name(rtime)
        else:
            carb_code = 'rescue'
        update = conn.cursor()
        logging.debug(f'{carbs} carbs at {str(rtime)} is {carb_code}')
        update.execute(f'''update {TABLE} 
                           set carbs = %s, carb_code = %s
                           where rtime = %s''',
                       [carbs, carb_code, rtime])
        if not debugp:
            conn.commit()

# ================================================================

def migrate_rescue_carbs(conn, start_time, 
                         end_time=date_ui.to_rtime(datetime.now()),
                         debug=False):
    '''import rescue_carbs from the janice.rescue_carbs table'''
    pass

def migrate_rescue_carbs_from_diamond(conn, start_time, 
                                      end_time=date_ui.to_rtime(datetime.now()),
                                      debug=False):
    '''import rescue_carbs from the janice.rescue_carbs_from_diamond table'''
    pass


# ================================================================

def valid_minutes_since_last_meal_before_time(conn, time):
    '''Returns the most recent valid tuple of rtime and minutes_since_last_meal
    that precedes the given time or None if none, but that shouldn't
    happen.
    '''
    curs = dbi.cursor(conn)
    curs.execute(f'''SELECT rtime, minutes_since_last_meal FROM {TABLE}
                     WHERE rtime = (SELECT max(rtime) FROM {TABLE} 
                                    WHERE rtime < %s
                                      AND minutes_since_last_meal is not null)''',
                 [time])
    return curs.fetchone()
    

def update_minutes_since_last_meal(conn, start_time,
                                   end_time=date_ui.to_rtime(datetime.now()),
                                   debug=False):
    '''This finds the most recent value that is before start_time and
    is valid and works forward from there, up to but preceding
    end_time. Hopefully, that value is very recent, but this might
    update many rows in some cases.

    '''
    # First, find the most recent non-null value for minutes_since_last_meal
    # we could ignore start_time, but let's look backwards from there
    try:
        start_time = date_ui.to_datetime(start_time)
        end_time = date_ui.to_datetime(end_time)
        valid_recent = valid_minutes_since_last_meal_before_time(conn, start_time)
        if valid_recent is None:
            logging.error(f'ERROR: no valid value of minutes_since_last_meal preceding {start_time}')
            return
        rtime, mm = valid_recent
        logging.debug(f'updating minutes_since_last_meal since {rtime} when it was {mm}')
        # Now, work forward, incrementing the counter and resetting it to
        # zero when there are non-rescue carbs
        curs = dbi.cursor(conn)
        while rtime < end_time:
            rtime += timedelta(minutes=5)
            curs.execute(f'''SELECT carb_code FROM {TABLE}
                             WHERE rtime = %s''',
                         [rtime])
            # notice the comma here; we're pulling the carb_code out of a tuple
            (carb_code,) = curs.fetchone()
            # print(rtime,carb_code)
            if carb_code is not None and carb_code != 'rescue':
                logging.debug(f'carb code {carb_code} at {rtime}')
                mm = 0
            else:
                mm += 5
            curs.execute(f'''UPDATE {TABLE} SET minutes_since_last_meal = %s
                             WHERE rtime = %s''',
                         [mm, rtime])
        if not debug:
            conn.commit()
    except Exception as err:
        msg = repr(err)
        logging.error(f'ERROR! {msg} in update_minutes_since_last_meal for input {start_time} and {end_time}')
        # raise err

# ================================================================

def valid_minutes_since_last_bolus_before_time(conn, time):
    '''Returns the most recent valid tuple of rtime and minutes_since_bolus
    that precedes the given time or None if none, but that shouldn't
    happen.
    '''
    curs = dbi.cursor(conn)
    curs.execute(f'''SELECT rtime, minutes_since_last_bolus FROM {TABLE}
                     WHERE rtime = (SELECT max(rtime) FROM {TABLE} 
                                    WHERE rtime < %s
                                      AND minutes_since_last_bolus is not null)''',
                 [time])
    return curs.fetchone()

def update_minutes_since_last_bolus(conn,
                                    start_time,
                                    end_time=date_ui.to_rtime(datetime.now()),
                                    debug=False):
    '''This finds the most recent value that is before start_time and
    is valid and works forward from there, up to but preceding
    end_time. Hopefully, that value is very recent, but this might
    update many rows in some cases.

    It would be more efficient to combine this function with other
    functions like update_minutes_since_last_meal, but (1) it's useful
    to test and run them separately, and (2) in practice, they will
    typically only run on a few rows.

    '''
    # First, find the most recent non-null value for minutes_since_last_meal
    # we could ignore start_time, but let's look backwards from there
    try:
        start_time = date_ui.to_datetime(start_time)
        end_time = date_ui.to_datetime(end_time)
        valid_recent = valid_minutes_since_last_bolus_before_time(conn, start_time)
        if valid_recent is None:
            logging.error(f'ERROR: no valid value of minutes_since_last_bolus preceding {start_time}')
            return
        rtime, mb = valid_recent
        logging.debug(f'updating minutes_since_last_bolus since {rtime} when it was {mb}')
        # Now, work forward, incrementing the counter and resetting it to
        # zero when there is a bolus, which we define as total_bolus_volume > 0
        curs = dbi.cursor(conn)
        while rtime < end_time:
            rtime += timedelta(minutes=5)
            curs.execute(f'''SELECT total_bolus_volume FROM {TABLE}
                             WHERE rtime = %s''',
                         [rtime])
            # notice the comma here; we're pulling the carb_code out of a tuple
            (tbv,) = curs.fetchone()
            if tbv is not None and tbv > 0:
                logging.debug(f'bolus of {tbv} at {rtime}')
                mb = 0
            else:
                mb += 5
            curs.execute(f'''UPDATE {TABLE} SET minutes_since_last_bolus = %s
                             WHERE rtime = %s''',
                         [mb, rtime])
        if not debug:
            conn.commit()
    except Exception as err:
        msg = repr(err)
        logging.error(f'ERROR! {msg} in update_minutes_since_last_bolus for input {start_time} and {end_time}')
        # raise err

# ================================================================

def update_corrective_insulin(conn, 
                              start_time,
                              end_time=date_ui.to_rtime(datetime.now()),
                              commit=True):
    '''In the interval, finds boluses (total_bolus_volume > 0) and
    checks if there are carbs within 30 minutes. If so, it's not
    corrective, otherwise it is.'''
    curs = conn.cursor()
    start_time = date_ui.to_rtime(start_time)
    end_time = date_ui.to_rtime(end_time)
    nr = curs.execute(f'''SELECT rtime FROM {TABLE}
                          WHERE rtime between %s and %s
                          AND total_bolus_volume is not null''',
                      [start_time, end_time])
    logging.info(f'{nr} boluses between {start_time} and {end_time}')
    for (rtime,) in curs.fetchall():
        near = conn.cursor()
        near.execute(f'''SELECT count(*) as meal FROM {TABLE}
                         WHERE rtime between %s and %s
                         AND carbs is not null''',
                     [rtime - timedelta(minutes=30),
                      rtime + timedelta(minutes=30)])
        (meal,) = near.fetchone()
        matched = ('matched' if meal == 1 else 'did not match')
        logging.debug(f'bolus at time {rtime} {matched} {meal} meal')
        update = conn.cursor()
        update.execute(f'''UPDATE {TABLE} SET corrective_insulin = %s
                           WHERE rtime = %s''',
                       [1-meal, rtime])
        if commit:
            conn.commit()

# ================================================================

# print('copy code for prime and refill from Milevas code')    

## ----------------------------- Tests ----------------------------------------

def test_conn(conn): 
    '''Test CRUD operations in autoapp/ janice databases''' 
    curs = conn.cursor()

    # Testing read operations of autoapp tables
    curs.execute('''select * from autoapp.basal_hour limit 5;''')
    results = curs.fetchall()
    print(results)

    # Testing create/delete operations of janice tables
    # curs.execute('''drop table if exists janice.mileva_test;''')
    # curs.execute('''create table janice.mileva_test like insulin_carb_smoothed_2;''')

def non_zero_duration_S_boluses(conn):
    curs = conn.cursor()
    curs.execute('''select bolus_id, date, type, value, duration 
                    from autoapp.bolus
                    where type = 'S' and duration > 5''')
    data = curs.fetchall()
    print('{} non-zero duration S events'.format(len(data)))
    for row in data:
        print((5*'{}\t').format(*row))

def zero_duration_E_boluses(conn):
    curs = conn.cursor()
    curs.execute('''select bolus_id, date, type, value, duration 
                    from autoapp.bolus
                    where type = 'E' and duration = 0''')
    data = curs.fetchall()
    print('{} zero-duration E events'.format(len(data)))
    for row in data:
        print((5*'{}\t').format(*row))

def simultaneous_bolus_and_basal(conn):
    curs = conn.cursor()
    curs.execute('''select *
                    from autoapp.bolus inner join autoapp.basal_hour 
                    on (bolus.date = basal_hour.date)''')
    data = curs.fetchall()
    print('{} simultaneous bolus and basal_hour events'.format(len(data)))
    for row in data:
        print((5*'{}\t').format(*row))

# ================================================================

def migrate_cgm(conn=None):
    '''This migrates any cgm values that we don't already have in ICS2. '''
    if conn is None:
        conn = dbi.connect()
    curs = dbi.cursor(conn)
    curs.execute('select max(rtime) from insulin_carb_smoothed_2 where cgm is not null');
    start_cgm = curs.fetchone()[0]
    logging.debug('migrating cgm data starting at {}'.format(start_cgm))
    curs.execute('''UPDATE insulin_carb_smoothed_2 AS ics 
                        INNER JOIN realtime_cgm2 AS rt USING (rtime)
                    SET ics.cgm = rt.mgdl
                    WHERE rtime >= %s''',
                 [start_cgm])
    conn.commit()
                    
# ================================================================
# migrate data since previous update

def get_migration_time(conn):
    '''Long discussion about the data to migrate. See
https://docs.google.com/document/d/1ZCtErlxRQmPUz_vbfLXdg7ap2hIz5g9Lubtog8ZqFys/edit#heading=h.umdjcuqs1gq4

This function looks up the values of autoapp.last_update.date (X) and
migration_status.prev_update (Y) and returns X,Y iff X < Y otherwise
None,None.

It returns both values so that Y can be stored into migration_status
when we are done migrating. See set_migration_time.

    5/29/2024 This stopped working at some point in the past. 

    '''
    curs = dbi.cursor(conn)
    curs.execute('''select date from autoapp.dana_history_timestamp where user_id = %s''',
                 [USER_ID])
    last_update = curs.fetchone()[0]
    curs.execute('''select prev_autoapp_update from migration_status where user_id = %s''',
                 [USER_ID])
    prev_update_row = curs.fetchone()
    if prev_update_row is None:
        raise Exception('no previous update stored')
    prev_update = prev_update_row[0]
    if prev_update < last_update:
        return prev_update, last_update
    else:
        return None, None

def init_migration_time(conn, force=False):
    '''Our normal code compares the prev_update (X) with last_update (Y)
and if X<Y, then there's new data to migrate and so we do so. But that
assumes that X exists. The Y value comes from autoapp; so that's not
our problem. But if X is missing we will initialize it by using
'2022-06-30 17:14', which I think is the last time I deleted the
commands table in Autoapp.

    '''
    curs = dbi.cursor(conn)
    curs.execute('''select prev_update from migration_status where user_id = %s''',
                 [USER_ID])
    prev_update = curs.fetchone()
    if prev_update is None or force:
        print('there is no previous update or forcing an overwrite. See documentation')
        old_time = '2022-06-30 17:14:00'
        curs.execute('''INSERT INTO migration_status(user_id,prev_update,migration_time)
                        VALUES (%s, %s, current_timestamp())
                        ON DUPLICATE KEY UPDATE prev_update = %s, migration_time = current_timestamp()''',
                     [USER_ID, old_time, old_time])
        conn.commit()

def set_migration_time(conn, prev_update_time, last_update_time):

    '''Long discussion about the data to migrate. See
https://docs.google.com/document/d/1ZCtErlxRQmPUz_vbfLXdg7ap2hIz5g9Lubtog8ZqFys/edit#heading=h.umdjcuqs1gq4

This function sets the value of prev_update_time in the janice
database from the value of last_update from autoapp. It uses the
passed-in values, to avoid issues of simultaneous.
    '''
    curs = dbi.cursor(conn)
    curs.execute('''UPDATE migration_status 
                    SET prev_autoapp_update = %s, prev_autoapp_migration = current_timestamp() 
                    WHERE user_id = %s''',
                 # notice this says last_ not prev_; we ignore prev here
                 [last_update_time, USER_ID])
    conn.commit()
    curs.execute('''INSERT INTO migration_log(user_id,prev_update,last_update,last_migration) 
                    VALUES(%s,%s,%s,current_timestamp())''',
                 [USER_ID, prev_update_time, last_update_time])
    conn.commit()
    return 'done'

# ================================================================
# this is the main function. It's divided into a function that
# migrates data for a given time range (so we can go back and
# re-calculate things if we need to, and June 2024, we do) and a
# function that updates the migration_time tables.

def migrate_between(conn, start_time, end_time):
    '''Migrates data that is in autoapp and other tables between those
    start/end times. This *does* do the fill-forward, so that any
    missing rows will be filled in. This should be idempotent.
    '''
    logging.info(f'migrate between {start_time} and {end_time}')
    fill_forward_between(conn, start_time, end_time)
    logging.info('migrate_basal_12')
    migrate_basal_12(conn, start_time, end_time)
    logging.info('bolus')
    bolus_import(conn, start_time, end_time)
    logging.info('carbohydrate')
    carbohydrate_import(conn, start_time, end_time)
    update_minutes_since_last_meal(conn, start_time, end_time)
    update_minutes_since_last_bolus(conn, start_time, end_time)
    update_corrective_insulin(conn, start_time, end_time)
    logging.info('done with migration')


def migrate_all(conn=None, alt_start_time=None):
    '''This is the function that should, eventually, be called from a cron job every 5 minutes.'''
    if conn is None:
        conn = dbi.connect()
    prev_update, last_update = get_migration_time(conn)
    if prev_update is None:
        logging.info('bailing because no updates')
        return
    start_time = alt_start_time or prev_update
    logging.info(f'start time is {start_time}')
    end_time = datetime.now()
    migrate_between(conn, start_time, end_time)
    logging.info('storing update time')
    set_migration_time(conn, prev_update, last_update)
    logging.info('done')

# ================================================================

def pm_data(conn, since):
    '''print all the migrated data we need for the predictive model,
namely basal_amt_12, bolus, carbs, and bg. Copy/paste into a
spreadsheet to share with Janice and Mileva

    '''
    curs = dbi.cursor(conn)
    n = curs.execute('''SELECT rtime, round(basal_amt_12*12,1) as basal_rate, 
                        bolus_type, total_bolus_volume, extended_bolus_amt_12,
                        carbs 
                        FROM {} WHERE rtime >= %s'''.format(TABLE),
                     [since])
    print('{} rows'.format(n))
    print("\t".join(['rtime','basal_rate',
                     'bolus_type', 'total_bolus_volume', 'extended_bolus_amt_12',
                     'carbs']))
    for row in curs.fetchall():
        print("\t".join(map(str,row)))


if __name__ == '__main__': 
    conn = dbi.connect()
    if len(sys.argv) > 1 and sys.argv[1] == 'reinit':
        create_test_tables(conn)    
        import_functions(conn)
    if len(sys.argv) > 1 and sys.argv[1] == 'since':
        migrate_all(conn, verbose=True, alt_start_time=sys.argv[2])
        sys.exit()
    # The default is to run as a cron job
    # when run as a script, log to a logfile 
    today = datetime.today()
    logfile = os.path.join(LOG_DIR, 'day'+str(today.day))
    logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s',
                        datefmt='%H:%M',
                        filename=logfile,
                        level=logging.DEBUG)
    logging.info('running at {}'.format(datetime.now()))
    migrate_all(conn)
    migrate_cgm(conn)
