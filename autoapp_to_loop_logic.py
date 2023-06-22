'''Migrates Hugh's records from the autoapp database to tables in the loop_logic database.

See https://docs.google.com/document/d/1n_lxiAqkgNiQgVSVidOo-5bntfIo5aQF/edit

realtime_cgm is migrated from janice.realtime_cgm2; that's separate
from all others, so it's pretty easy.

Next, we migrate all bolus and carb data for the last max_bolus_interval (a
field in the glucose range table).  Use 6 hours if missing.

Testing: start python, and run the functions in ...

dest = 'loop_logic'
src = 'autoapp'
a.migrate_all(conn, src, dest, '2023-01-01', True)

Changelog:

January 10 2023. Added flexibility vary SOURCE and DEST: 
  SOURCE = autoapp or autoapp_test
  DEST = loop_logic or autoapp_test 
respectively

Jan 13 2023. Changed migration time computation so that instead of
looking back to the last migration, it just looks back based on the
configuration timeout limits, currently 40 minutes for commands and 6
hours for other tables.

This was because a single command back in December broke the algorithm
forever, because it kept trying and failing. Might as well move on.

Jan 19, 2023, rewrote the bolus migration to pick up the commands as
well as the entries in the bolus table: "Yes, there are boluses in the
command table and boluses that are only in the bolus table.  The
latter were initiated on the pump itself and not through a parent
command.  Both the overlapping (command table + bolus table) and the
“just in bolus table” should be transferred to loop summary."

May 12, 2023 We want to be get the matching cgm value from *either*
janice.realtime_cgm2 or {dest}.latest_cgm, the latter when we are
testing, which we can determine by looking at the status field of the
{dest}.testing_command table. I modified matching_cgm to do that.

May 18, 2023. Scratch the previous. Let's get the matching CGM value
from {dest}.realtime_cgm, which will *either* be the real data or the
fake data. As long as the CGM values are

May 19, 2023. Janice said that for bolus and carbs to be matched to
each other, they should be within *5* minutes, not 30. That will
vastly decrease the chance that we will have multiple matches and,
furthermore, we won't have to worry about one entry in loop_summary
trying to comprise multiple boluses and/or multiple carbs.

'''

import os                       # for path.join
import sys
import math                     # for floor
import collections              # for deque
import cs304dbi as dbi
from datetime import datetime, timedelta
import date_ui
import logging

from loop_logic_testing_cgm_cron import in_test_mode as in_loop_logic_test_mode
import loop_logic_testing_cgm_cron as lltcc


# Configuration Constants

# probably should have different logs for production vs development
LOG_DIR = '/home/hugh9/autoapp_to_loop_logic_logs/'

HUGH_USER = 'Hugh'
HUGH_USER_ID = 7
MATCHING_BOLUS_INTERVAL = 30    # minutes between command and bolus to match them.
OTHER_DATA_TIMEOUT = 6*60       # minutes to look back for non-command (bolus, carbs)
MATCHING_BOLUS_WITH_CARB_INTERVAL = 5 # minutes between bolus and carbs to match them and put them in a single loop_summary entry. 

# the time in minutes for two timestamps to "match"
TIMEDELTA_MINS = 5

def debugging():
    '''Run this in the Python REPL to turn on debug logging. The default is just error'''
    logging.basicConfig(level=logging.DEBUG)

# this is copied from dexcom_cgm_sample.py
# we should consider storing this useful value

def get_latest_stored_data(conn):
    '''Looks up the latest data that we stored from previous inquiries.
Returns rtime and dexcom_time from last non-NULL value. We can infer
the number of values we need from Dexcom from those.

    '''
    curs = dbi.cursor(conn)
    curs.execute('''SELECT rtime, dexcom_time
                    FROM janice.realtime_cgm2
                    WHERE user_id = %s and
                          rtime = (SELECT max(rtime) FROM janice.realtime_cgm2
                                   WHERE user_id = %s and mgdl is not NULL)''',
                 [HUGH_USER_ID, HUGH_USER_ID])
    row = curs.fetchone()
    return row



def get_cgm_update_times(conn, dest):
    '''Long discussion about the data to migrate. See
https://docs.google.com/document/d/1ZCtErlxRQmPUz_vbfLXdg7ap2hIz5g9Lubtog8ZqFys/edit#heading=h.umdjcuqs1gq4

This function also looks in the janice.realtime_cgm2 table and finds
the most recent value where mgdl is not None (Y). We should probably
store that useful value somewhere. It also returns the prior value of
that, we stored as DEST.migration_status.prev_cgm_update
(PY). Returns both (Y,PY) if Y > Py, otherwise None, None.

    '''
    (rtime, dexcom_time) = get_latest_stored_data(conn)
    last_cgm = min(rtime, dexcom_time)
    curs = dbi.cursor(conn)
    curs.execute(f'''select prev_cgm_update from {dest}.migration_status where user_id = %s''',
                 [HUGH_USER_ID])
    prev_cgm = curs.fetchone()[0]
    logging.debug(f'last update from dexcom was at {last_cgm}; the previous value was {prev_cgm}')
    if prev_cgm < last_cgm:
        # new data, so return the time to migrate since
        return prev_cgm, last_cgm # increasing order
    else:
        return None, None
    

def set_cgm_migration_time(conn, dest, prev_update, last_update):
    '''Long discussion about the data to migrate. See
https://docs.google.com/document/d/1ZCtErlxRQmPUz_vbfLXdg7ap2hIz5g9Lubtog8ZqFys/edit#heading=h.umdjcuqs1gq4

This function sets the value of prev_update_time in the
DEST.migration_status table to the time of the latest real data in janice.realtime_cgm2.

It uses the passed-in values, to avoid issues of simultaneous updates. Ignores prev_update, uses last_update

    '''
    logging.debug(f'setting prev {prev_update} and last {last_update} cgm update times')
    curs = dbi.cursor(conn)
    curs.execute(f'''UPDATE {dest}.migration_status 
                    SET prev_cgm_update = %s, prev_cgm_migration = current_timestamp() 
                    WHERE user_id = %s''',
                 # notice this says last_ not prev_; we ignore prev here
                 [last_update, HUGH_USER_ID])
    conn.commit()
    return 'done'

def get_autoapp_update_times(conn, source, dest):
    '''Long discussion about the data to migrate. See
https://docs.google.com/document/d/1ZCtErlxRQmPUz_vbfLXdg7ap2hIz5g9Lubtog8ZqFys/edit#heading=h.umdjcuqs1gq4

Note that the dana_history_timestamp table records the time that data
(bolus, carbs) was last posted to autoapp from the child pump. So this
function returns times for migration of data (bolus, carbs), not for
commands or for CGM.

This function looks up the values of
SOURCE.dana_history_timestamp.date (X) and
DEST.migration_status.prev_autoapp_update (PX) and returns (X, PX)
iff X > PX otherwise None,None.

It returns all values so that new values can be stored into
migration_status when we are done migrating. See set_migration_time.

    '''
    curs = dbi.cursor(conn)
    curs.execute(f'''select date from {source}.dana_history_timestamp where user_id = %s''',
                 [HUGH_USER_ID])
    row = curs.fetchone()
    if row is None:
        logging.error(f'no value in {source}.dana_history_timestamp')
        return None, None
    last_autoapp_update = row[0]
    curs.execute(f'''select prev_autoapp_update from {dest}.migration_status where user_id = %s''',
                 [HUGH_USER_ID])
    row = curs.fetchone()
    if row is None:
        logging.error(f'no value in {dest}.migration_status')
        return None, None
    prev_autoapp = row[0]
    if prev_autoapp < last_autoapp_update:
        # new data since last migration, so return the time to migrate since
        return prev_autoapp, last_autoapp_update # increasing order
    else:
        return None, None

def set_autoapp_migration_time(conn, dest, prev_update, last_update):
    '''Long discussion about the data to migrate. See
https://docs.google.com/document/d/1ZCtErlxRQmPUz_vbfLXdg7ap2hIz5g9Lubtog8ZqFys/edit#heading=h.umdjcuqs1gq4

This function sets the value of prev_autoapp_update in the
loop_logic.migration_status table to the time of the lastest real data
in autoapp.dana_history_timestamp

It uses the passed-in values, to avoid issues of simultaneous updates.

    '''
    logging.debug(f'setting prev {prev_update} and last {last_update} autoapp update times')
    curs = dbi.cursor(conn)
    curs.execute(f'''UPDATE {dest}.migration_status 
                    SET prev_autoapp_update = %s, prev_autoapp_migration = current_timestamp() 
                    WHERE user_id = %s''',
                 # notice this says last_ not prev_; we ignore prev here
                 [last_update, HUGH_USER_ID])
    conn.commit()
    return 'done'


# ================================================================

def migrate_cgm(conn, dest, start_time, commit=True):
    '''start_time is a string or a python datetime. '''
    if conn is None:
        conn = dbi.connect()
    curs = dbi.cursor(conn)
    logging.debug(f'migrating realtime_cgm since {start_time}')
    # must use rtime, not dexcom_time, since the latter can be null
    # but we retrieve the dexcom_time, to be be consistent with {dest}.realtime_cgm
    nrows = curs.execute('''select user_id, dexcom_time, mgdl, trend, trend_code
                            from janice.realtime_cgm2
                            where rtime > %s and mgdl is not NULL''',
                         [start_time])
    logging.debug(f'got {nrows} from realtime_cgm2')
    ins = dbi.cursor(conn)
    for row in curs.fetchall():
        # we can't use on duplicate key, because the key is an auto_increment value that we don't have.
        # So we have to look for matches on timestamp values. 
        (user_id, dexcom_time, _, _, _) = row
        nr = ins.execute(f'''select cgm_id from {dest}.realtime_cgm 
                             where user_id = %s and dexcom_time = %s''',
                         [user_id, dexcom_time])
        logging.debug(f'found {nr} matches (already migrated rows)')
        if nr == 0:
            ins.execute(f'''insert into {dest}.realtime_cgm(cgm_id,user_id,dexcom_time,mgdl,trend,trend_code,src)
                           values(null,%s,%s,%s,%s,%s,'real')''',
                        row)
    if commit:
        conn.commit()

def migrate_cgm_test(conn, start_time, dest='loop_logic'):
    if conn is None:
        conn = dbi.connect()
    curs = dbi.cursor(conn)
    curs.execute(f'select count(*) from {dest}.realtime_cgm;')
    count_before = curs.fetchone()[0]
    print(f'before, there are {count_before}')
    # don't commit when testing. It'll be true in this connection, but not permanent
    migrate_cgm(conn, dest, start_time, False)
    curs.execute(f'select count(*) from {dest}.realtime_cgm;')
    count_after = curs.fetchone()[0]
    print(f'after, there are {count_after}')

def try_in_loop_logic_test_mode(conn, dest):
    try:
        return in_loop_logic_test_mode(conn, dest)
    except Exception as error:
        logging.debug("error in 'in_loop_logic_test_mode':  "+str(error))
        return False
        
def migrate_cgm_updates(conn, dest):
    '''migrate all the new cgm values, since the last time we migrated.
5/18 calls imported function in_test_mode to determine whether a test
is running in dest.

    '''
    if try_in_loop_logic_test_mode(conn, dest):
        logging.debug(f'skipping cgm migration because in test mode for {dest}')
        return
    prev_cgm_update, last_cgm_update = get_cgm_update_times(conn, dest)
    if prev_cgm_update is None:
        logging.debug('no new cgm data to migrate')
        return
    migrate_cgm(conn, dest, prev_cgm_update)
    set_cgm_migration_time(conn, dest, prev_cgm_update, last_cgm_update)

# ================================================================
# Bolus functions

# this function seems no longer to be used
def get_max_bolus_interval_mins(conn, dest, user_id=HUGH_USER_ID):
    '''Look up the max_bolus_interval in the glucose_range table for the given user_id'''
    if conn is None:
        conn = dbi.connect()
    curs = dbi.cursor(conn)
    DEFAULT = 6*60
    return DEFAULT
    nrows = curs.execute(f'''select max_bolus_interval_mins 
                            from {dest}.glucose_range inner join {dest}.user using(glucose_range_id)
                            where user_id = %s''',
                         [user_id])
    if nrows == 0:
        return DEFAULT
    row = curs.fetchone()
    if row is None:
        return DEFAULT
    return row[0]
        
def matching_cgm(conn, dest, timestamp, test_mode=False):
    '''Returns two values, the cgm_id and cgm_value value from the
{dest}.realtime_cgm table where its timestamp is closest in time to the given
timestamp, which is the timestamp of a bolus or a command.
{dest} is a database like loop_logic

Apr 8/2023, replaced the algorithm to use the algorithm in closest_time.sql
Using 1 hour as the max time interval for a match to count.

Apr 8/2023, But this should probably be replaced by just getting a
window of rows around the given time and searching within Python.

May 12, 2023. Added a keyword arg to indicate where to look for the
linked cgm, so that we can test this function by looking for matching
values in janice.realtime_cgm2.

May 18, 2023. Removed that keyword, because we will always search
realtime_cgm. Added a test_mode keyword to be more verbose.

    '''
    curs = dbi.cursor(conn)
    MM = MAX_MINUTES_FOR_MATCHING_CGM = 30
    # 5/12 New algorithm: get all values within that range and then find closest in Python
    # This might be re-written more concisely using the BETWEEN operator, but this is equivalent
    query = f'''SELECT cgm_id, dexcom_time, mgdl from {dest}.realtime_cgm
               WHERE user_id = %s AND 
               (%s - interval {MM} minute) < dexcom_time and 
               dexcom_time < (%s + interval {MM} minute)'''
    nr = curs.execute(query, [HUGH_USER_ID, timestamp, timestamp])
    if nr == 0:
        logging.error(f'no matching CGM for timestamp {timestamp}')
        return (None, None)
    rows = curs.fetchall()
    timestamp = date_ui.to_datetime(timestamp)
    if test_mode:
        print(f'found {len(rows)} rows for time {timestamp}')
    (cgm_id, cgm_time, mgdl) = argmin(rows, lambda row : abs(row[1]-timestamp))
    logging.debug(f'found matching CGM for timestamp {timestamp}: {cgm_time} id = {cgm_id}, mgdl = {mgdl}')
    return (cgm_id, mgdl)

def test_matching_cgm(conn, dest, test_time):
    '''test given timestamp'''
    cgm_id, mgdl = matching_cgm(conn, dest, test_time, test_mode=True)

def test_matching_cgm_all(conn, dest):
    '''test every timestamp between start_time and end_time by steps of 5
minutes. Returns (1) the number of successes (non-null values) from
(2) the total number of rows and (3) the times with no match. The
latter can be investigated individually, but mostly, we're looking to
see if there are any runtime errors.

    '''
    curs = dbi.cursor(conn)
    curs.execute(f'select min(dexcom_time), max(dexcom_time) from {dest}.realtime_cgm')
    (st, et) = curs.fetchone()
    print(f'trying all values from {st} to {et}')
    num_non_null = 0
    total_num = 0
    no_match = []
    while st < et:
        cgm_id, mgdl = matching_cgm(conn, dest, st)
        total_num += 1
        if mgdl is not None:
            num_non_null += 1
        else:
            no_match.append(st)
        st += timedelta(minutes=5)
    return (num_non_null, total_num, no_match)

def get_boluses(conn, source, start_time):
    '''Return a list of recent boluses (anything after start_time) as a
list of tuples. We only need to look at the bolus table, since
we just want bolus_pump_id, date, value and type. If the bolus ends up
being associated with a command, we'll update the entry later.

    '''
    curs = dbi.cursor(conn)
    # ignore type and duration?
    # note: bolus_id is called bolus_pump_id in loop_logic
    curs.execute(f'''select user_id, bolus_id, date, value 
                    from {source}.bolus
                    where date >= %s''',
                 [start_time])
    return curs.fetchall()
    
# reference for the code later
'''
  `bolus_id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `date` datetime NOT NULL,
  `type` varchar(2) NOT NULL,
  `value` double NOT NULL,
  `duration` double NOT NULL,
  `server_date` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
'''


def fix_missing_bolus_timestamps(conn, source, dest, commit=True):
    '''this is a nonce function to fix older missing bolus timestamps. As
of 1/27/2023, it didn't match anything since 1/20/2023.'''
    curs = dbi.cursor(conn)
    curs.execute(f'''select loop_summary_id, bolus_pump_id, bolus_value from {dest}.loop_summary
                     where bolus_value > 0
                       and bolus_timestamp is null''')
    rows = curs.fetchall()
    print(f'{len(rows)} null bolus_timestamps')
    for row in rows:
        print(row)
    for ls_id, bolus_id, bolus_value in rows:
        if bolus_id is None:
            print('null bolus_id')
            continue
        curs.execute(f'select date from {source}.bolus where bolus_id = %s', [bolus_id])
        bolus_rows = curs.fetchall()
        print(ls_id, bolus_id, '=>', bolus_rows)
        if len(bolus_rows) == 0:
            print('weird, no such bolus_id', bolus_id)
        elif len(bolus_rows) > 1:
            print('weird, multiple matches', bolus_id)
        else:
            num_update = curs.execute(f'''update {dest}.loop_summary 
                                          set bolus_timestamp = %s 
                                          where loop_summary_id = %s''',
                                      [bolus_rows[0][0], ls_id])
            if num_update != 1:
                print('weird: number updated is not one', num_update)
            if commit:
                conn.commit()
    print('done')


def carbs_within_interval(conn, source, dest, timestamp, interval_width):
    '''returns loop_summary_id, carb_id, carb_timestamp, carb_value
searching for carb value in loop_summary within plus or minus
interval_width of timestamp. Returns None if no match.

    '''
    if conn is None:
        conn = dbi.connect()
    curs = dbi.cursor(conn)
    nr = curs.execute(f'''SELECT loop_summary_id, carb_id, carb_timestamp, carb_value 
                          FROM {dest}.loop_summary 
                          WHERE user_id = %s  
                          AND carb_timestamp 
                          BETWEEN (%s - interval %s minute) 
                              AND (%s + interval %s minute)''',
                 [HUGH_USER_ID, timestamp, interval_width, timestamp, interval_width])
    rows = curs.fetchall()
    # hopefully the normal case
    if nr == 1:
        return rows[0]
    if nr == 0:
        logging.debug(f'no carbs in interval around {timestamp}')
        return None
    if nr > 1:
        logging.debug(f'multiple carbs in interval around {timestamp}; using largest')
        biggest = argmax(rows, lambda r: r[3])
        return biggest

def carbs_within_interval_test(conn, source, dest, start_time, width=5):
    '''This is for basic robustness and correctness. Modifies no data, so safe to use in any database.'''
    if conn is None:
        conn = dbi.connect()
    curs = dbi.cursor(conn)
    for bolus_row in get_boluses(conn, source, start_time):
        (user_id, bolus_pump_id, bolus_time, value) = bolus_row
        match = carbs_within_interval(conn, source, dest, bolus_time, width)
        if match is None:
            print(f'correction bolus at {bolus_time}')
        else:
            (id, carb_id, carb_time, carb_value) = match
            diff = abs(date_ui.to_datetime(bolus_time) - date_ui.to_datetime(carb_time))
            if diff.total_seconds() >= width*60:
                print(f'ERROR at {start_time}')
                print(f'{id}, {carb_id}, {carb_time}, {carb_value}')
                raise Exception
            print(f'loop summary id {id} for carb_id {carb_id} matches')
        
def migrate_boluses(conn, source, dest, start_time, commit=True):
    '''start_time is a string or a python datetime. '''
    if conn is None:
        conn = dbi.connect()
    curs = dbi.cursor(conn)
    # Note that these will probably be *new* rows, but to make this
    # idempotent, we'll look for a match on the date.
    boluses = get_boluses(conn, source, start_time)
    n = len(boluses)
    logging.info(f'{n} boluses to migrate since {start_time}')
    for row in boluses:
        # note: bolus_id is called bolus_pump_id in loop_logic
        (user_id, bolus_pump_id, date, value) = row
        # see if bolus_pump_id matches, to avoid re-inserting something already migrated
        curs.execute(f'''select loop_summary_id, user_id, bolus_pump_id, bolus_timestamp, bolus_value
                        from {dest}.loop_summary
                        where user_id = %s and bolus_pump_id = %s''',
                     [user_id, bolus_pump_id])
        match = curs.fetchone()
        if match is None:
            # the normal case, we'll insert it. First see if there's a CGM at this time
            (cgm_id, mgdl) = matching_cgm(conn, dest, date)
            # next, see if there are carbs w/in an interval.
            # 5/19. Get info about the carbs, to fill into loop_summary fields
            carb_row = carbs_within_interval(conn, source, dest, date, MATCHING_BOLUS_WITH_CARB_INTERVAL)
            if carb_row is None:
                logging.debug(f'CASE C: migrate bolus at time {date} has no matching carbs')
                # have to insert into loop_summary
                bolus_type = 'correction' # since no carbs
                curs.execute(f'''INSERT INTO {dest}.loop_summary
                                (user_id, bolus_pump_id, bolus_timestamp, bolus_type, bolus_value,
                                linked_cgm_id, linked_cgm_value                                
                                )
                            values(%s, %s, %s, %s, %s, %s, %s)''',
                         [user_id, bolus_pump_id, date, bolus_type, value, cgm_id, mgdl])
                # since it's a correction, check if it's an anchor or top-up
                identify_anchor_bolus(conn, source, dest, date)
            else:
                # since there are matching carbs, update that row instead
                # we actually don't need the other data, since it's already in the row
                (loop_summary_id, carb_id, carb_timestamp, carb_value) = carb_row
                logging.debug(f'CASE D: migrate bolus at time {date} has matching carbs {carb_value} at time {carb_timestamp}')
                bolus_type = 'carb'
                curs.execute(f'''UPDATE {dest}.loop_summary
                                 SET bolus_pump_id = %s, bolus_timestamp = %s, bolus_type = %s, bolus_value = %s,
                                     linked_cgm_id = %s, linked_cgm_value = %s
                                 WHERE loop_summary_id = %s''',
                         [bolus_pump_id, date, bolus_type, value, cgm_id, mgdl, loop_summary_id])
                
        else:
            # already exists, so update? Ignore? We'll complain if they differ
            logging.info('bolus match: this bolus is already migrated: {}'.format(row))
            
    if commit:
        conn.commit()
    
def migrate_boluses_test(conn, source, dest, start_time, commit=True):
    curs = dbi.cursor(conn)
    nr = curs.execute('''select carb_timestamp from lltt.loop_summary where carb_timestamp is not null''')
    print(f'{nr} carbs for testing')
    carb_times = [r[0] for r in curs.fetchall()]
    migrate_boluses(conn, source, 'lltt', start_time, commit=commit)

def nonce_merge_boluses_with_carbs(conn, dest, start_time, end_time):
    pass


def bytes_to_int(bytes_val):
    '''0/1 values are stored in autoapp as single-byte quantities,
actually bit(1). They come into Python as byte arrays of length
1. This converts to nice integers.'''
    if type(bytes_val) is int:
        return bytes_val
    if type(bytes_val) is bytes:
        if len(bytes_val) == 1:
            int_val = int.from_bytes(bytes_val, "big")
            return int_val
        raise ValueError(f'multi-byte value: {bytes_val}')
    raise TypeError(f'not either int or bytes: {bytes_val}')

def argmin(seq, func):
    '''Return the element of seq for which func is smallest. Returns None
if seq is empty.'''
    if len(seq) == 0:
        return None
    best = seq[0]
    best_val = func(best)
    for elt in seq:
        elt_val = func(elt)
        if elt_val < best_val:
            best, best_val = elt, elt_val
    return best

def argmin_test():
    seq = [ {'i': i, 'y': (i-5)*(i-5)} for i in range(10) ]
    for val in seq:
        print(val)
    print('smallest i', argmin(seq, lambda e: e['i']))
    print('smallest y', argmin(seq, lambda e: e['y']))


def matching_bolus_row_within(conn, source, timestamp, interval_minutes=30):
    '''Returns the row (as a dictionary) from the `autoapp.bolus` table
    closest in time to the given timestamp and within the given
    interval.  While it's possible to do the query entirely in the
    database, I'm not sure it's worth it. The query is very complex
    and it's almost certainly easier to fetch the 12 rows around the
    timestamp to Python and find the best match, if any, here. So,
    that's what I've done.
    '''
    curs = dbi.dict_cursor(conn)
    query = f'''SELECT bolus_id, user_id, date, type, value, duration, server_date 
               FROM {source}.bolus
               WHERE user_id = %s 
                 AND date between (%s - interval %s minute) AND (%s + interval %s minute)
            '''
    nr = curs.execute(query, [HUGH_USER_ID,
                              timestamp, interval_minutes,
                              timestamp, interval_minutes])

    if nr == 0:
        # No boluses within time interval, so just return None
        return None
    # Okay, a little work to do
    rows = curs.fetchall()
    timestamp = date_ui.to_datetime(timestamp)
    closest = argmin(rows, lambda row : abs(row['date']-timestamp))
    return closest

def migrate_commands(conn, source, dest, alt_start_time=None, commit=True,
                     loop_summary_table='loop_summary'):
    '''Migrate commands within the last 40". '''
    if conn is None:
        conn = dbi.connect()
    read = dbi.cursor(conn)
    start = (alt_start_time
             if alt_start_time is not None
             else datetime.now() - timedelta(minutes=40))
    start = date_ui.to_rtime(start)
    logging.info(f'migrating commands since {start}')
    num_com = read.execute(
        f'''SELECT command_id, user_id, created_timestamp, type, 
                  if(completed,1,0) as comp,
                  if(error,1,0) as err,
                  state, 
                  if(pending,1,0) as pend, 
                  if(loop_command,1,0) as lc, 
                  if(parent_decision,1,0) as pd, 
                  sb.amount as sb_amount,
                  tb.ratio as tb_ratio
           FROM {source}.commands 
                LEFT OUTER JOIN {source}.commands_single_bolus_data AS sb USING(command_id)
                LEFT OUTER JOIN {source}.commands_temporary_basal_data AS tb USING(command_id)
           WHERE created_timestamp > %s''',
        [start])
    logging.info(f'{num_com} commands to migrate')
    update = dbi.cursor(conn)
    for row in read.fetchall():
        row_str = ','.join([str(e) for e in row])
        logging.debug(f'migrating row {row_str}')
        # shorthands for the column names above
        (cid, uid, ct, ty, comp, err, state, pend, lc, pd, sb_amt, tb_ratio) = row
        if cid is None:
            raise Exception('NULL cid')
        ## compute parent_involved as a simple boolean
        parent_involved = 0 if lc == 1 and pd == 0 else 1
        ## Find matching cgm for this created_timestamp
        (cgm_id, cgm_value) = matching_cgm(conn, dest, ct)
        ## 
        '''If ‘completed’=1, the bolus command should be matched to a row
        with a ‘bolus_pump_id’.  Match can be done by closest
        timestamp.  In addition, the ‘bolus_value’ of the
        ‘bolus_pump_id’ row should be the same as the
        ‘amount_delivered’ in the “commands_single_bolus” table with
        the associated ‘command_id’.  The ‘settled’ field should be
        set to 1 (matching and completed).  If not completed, and
        ‘error’=1, bring it over but it will have no match and the
        ‘settled’ field should be set to 3.  If ‘completed’ =0 and
        ‘error’=0, bring it over and set ‘settled’ field to 0.
        '''
        if comp == 1 and ty == 'bolus':
            # find closest matching timestamp in `bolus`
            # table. Originally, Janice said within 30 minutes
            # (checking realtime_cgm). Then on 12/1 she said "I spoke
            # to Hugh--he never puts a glucose value into the pump or
            # the app when he corrects so if no CGM, there will be
            # nothing else to use."
            bolus_row = matching_bolus_row_within(conn, source, ct, MATCHING_BOLUS_INTERVAL)
            # might return None, so guard with (bolus_row AND expr)
            bolus_pump_id = bolus_row and bolus_row['bolus_id']
            bolus_value = bolus_row and bolus_row['value']
        else:
            bolus_pump_id = None
            bolus_value = None
        # So, now we have a bolus_value but we also have a sb_amt from
        # the commands_single_bolus_data table.  are these the same?

        # check if command is already there (migrated earlier) by checking command_id
        nrows = update.execute(f'''SELECT loop_summary_id 
                                   FROM {dest}.{loop_summary_table} 
                                   WHERE command_id = %s''',
                               [cid])
        if nrows > 0:
            loop_summary_id = update.fetchone()[0]
            # eventually, I think we just skip a row that has been
            # migrated, because we'll do things right the first time.
            logging.info(f'command {cid} at time {ct} has already been migrated as {loop_summary_id}; updating it')
            update.execute(f'''UPDATE {dest}.{loop_summary_table}
                              SET user_id = %s, bolus_pump_id = %s, bolus_value = %s, command_id = %s, 
                                  created_timestamp = %s, state = %s, type = %s, pending = %s, completed = %s,
                                  error = %s, loop_command = %s, parent_decision = %s, 
                                  linked_cgm_id = %s, linked_cgm_value = %s, 
                                  parent_involved = %s
                              WHERE loop_summary_id = %s;''',
                           [uid, bolus_pump_id, sb_amt, cid, ct, state, ty, pend, comp, err, lc, pd,
                            cgm_id, cgm_value,
                            parent_involved,
                            loop_summary_id])
        else:
            ## 12 columns, first being NULL, the rest are migrated data,
            ## in order of the fields in loop_summary_table
            update.execute(f'''INSERT INTO {dest}.{loop_summary_table}
                                 (loop_summary_id,
                                 user_id,
                                 bolus_pump_id,
                                 bolus_value,
                                 command_id,
                                 created_timestamp,
                                 state,
                                 type,
                                 pending,
                                 completed,
                                 error,
                                 loop_command,
                                 parent_decision,
                                 linked_cgm_id,
                                 linked_cgm_value,
                                 parent_involved) VALUES 
                               (NULL, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''',
                           [uid, bolus_pump_id, sb_amt, cid, ct, state, ty, pend, comp, err, lc, pd,
                            cgm_id, cgm_value, parent_involved])
        # after either INSERT or UPDATE
        if commit:
            conn.commit()

def test_migrate_commands(conn, source, dest, alt_start_time, commit):
    '''this uses a test table that is a copy of the structure of the real
    loop_logic.loop_summary table'''
    if conn is None:
        conn = dbi.connect()
    curs = dbi.cursor(conn)
    TABLE = 'test_loop_summary'
    curs.execute(f'drop table if exists {dest}.{TABLE}')
    curs.execute(f'create table {dest}.{TABLE} like {dest}.loop_summary')
    conn.commit()
    migrate_commands(conn, source, dest, alt_start_time, commit,
                     loop_summary_table=TABLE)
    # curs.execute(f'select * from {dest}.{TABLE}')
    curs.execute(f'select loop_summary_id, command_id, state, type, pending, loop_command, parent_decision from {dest}.{TABLE}')
    print('after migration')
    for row in curs.fetchall():
        print(row)

def re_migrate_commands(conn, source, dest, alt_start_time, commit):
    '''clearing out previously migrated commands and re-doing them, when
there are significant upgrades to the algorithm.'''
    curs = dbi.cursor(conn)
    # clear out the old
    nr = curs.execute(f'''DELETE FROM {dest}.loop_summary 
                         WHERE command_id IS NULL or
                               command_id IN (SELECT command_id 
                                              FROM {source}.commands
                                              WHERE created_timestamp >= %s)''',
                 [alt_start_time])
    print(f'deleting {nr} commands from loop_summary since {alt_start_time}')
    if commit:
        conn.commit()
    # remigrate
    migrate_commands(conn, source, dest, alt_start_time, commit)

## ================================================================

def get_carbs(conn, source, start_time):
    '''pull rows from {source}.carbohydrate'''
    curs = dbi.cursor(conn)
    # note: carbohydrate_id is called carb_id in loop_summary
    curs.execute(f'''select user_id, carbohydrate_id, date, value 
                    from {source}.carbohydrate
                    where date >= %s''',
                 [start_time])
    return curs.fetchall()

def bolus_within_interval(conn, source, dest, timestamp, interval_width):
    '''returns loop_summary_id, bolus_pump_id, bolus_timestamp,
type_bolus_value searching for bolus in loop_summary within plus or
minus interval_width of timestamp. Returns None if no match.

    '''
    if conn is None:
        conn = dbi.connect()
    curs = dbi.cursor(conn)
    nr = curs.execute(f'''SELECT loop_summary_id, bolus_pump_id, bolus_timestamp, bolus_value 
                          FROM {dest}.loop_summary 
                          WHERE user_id = %s  
                          AND bolus_timestamp 
                          BETWEEN (%s - interval %s minute) 
                              AND (%s + interval %s minute)''',
                 [HUGH_USER_ID, timestamp, interval_width, timestamp, interval_width])
    rows = curs.fetchall()
    # hopefully the normal case
    if nr == 1:
        return rows[0]
    if nr == 0:
        logging.debug(f'no bolus in interval around {timestamp}')
        return None
    if nr > 1:
        logging.debug(f'multiple boluses in interval around {timestamp}; using largest')
        biggest = argmax(rows, lambda r: r[3])
        return biggest


def migrate_carbs(conn, source, dest, start_time, commit=True):
    '''Like the other migrations. start_time is string or python datetime.'''
    if conn is None:
        conn = dbi.connect()
    curs = dbi.cursor(conn)
    # Note that these will probably be *new* rows, but to make this
    # idempotent, we'll look for a match on the date.
    carbs = get_carbs(conn, source, start_time)
    n = len(carbs)
    logging.info(f'{n} carbs to migrate since {start_time}')
    for row in carbs:
        # note: carb_id is called carbohydrate_id in the source
        (user_id, carb_id, carb_date, value) = row
        # see if carb_id matches, to avoid re-inserting something already migrated
        curs.execute(f'''select loop_summary_id, user_id, carb_id
                        from {dest}.loop_summary
                        where user_id = %s and carb_id = %s''',
                     [user_id, carb_id])
        match = curs.fetchone()
        if match is None:
            # the normal case, we'll insert it. First see if there's a CGM at this time
            (cgm_id, cgm_value) = matching_cgm(conn, dest, carb_date)
            # 5/23. Get info about the carbs at this time. If so, use that row.
            bolus_row = bolus_within_interval(conn, source, dest, carb_date, MATCHING_BOLUS_WITH_CARB_INTERVAL)
            if bolus_row is None:
                logging.debug(f'CASE A: new carbs, no matching bolus')
                curs.execute(f'''insert into {dest}.loop_summary
                                 (user_id, carb_id, carb_timestamp, carb_value, linked_cgm_id, linked_cgm_value)
                                 values(%s, %s, %s, %s, %s, %s)''',
                             [user_id, carb_id, carb_date, value, cgm_id, cgm_value])
            else:
                # reuse existing row. Note that this revision means
                # that the bolus is now associated with carbs, so
                # change its type to 'carb' and its anchor to NULL
                (loop_summary_id, bolus_pump_id, bolus_timestamp, bolus_value) = bolus_row
                logging.debug(f'CASE B. migrate carbs at time {carb_date} has matching bolus {bolus_pump_id} at time {bolus_timestamp}')
                bolus_type = 'carb'
                curs.execute(f'''UPDATE {dest}.loop_summary
                                 SET carb_id = %s, carb_timestamp = %s, carb_value = %s, 
                                     bolus_type = 'carb', anchor = NULL,
                                     linked_cgm_id = %s, linked_cgm_value = %s
                                 WHERE loop_summary_id = %s''',
                         [carb_id, carb_date, value, cgm_id, cgm_value, loop_summary_id])

        else:
            # already exists, so update? Ignore? We'll complain if they differ
            logging.info('carb match: this carb is already migrated: {}'.format(row))
    if commit:
        conn.commit()

# This function is not currently used. 
def migrate_carbs_to_bolus(conn, source, dest, start_time, commit=True):
    '''This version looks for row with a bolus within 30 (configurable)
minutes and updates that row to put the carbs into that.  If the carbs
are within 30 minutes of *now*, they might have preceded the bolus, in
which case go ahead and insert.'''
    if conn is None:
        conn = dbi.connect()
    curs = dbi.cursor(conn)
    # Note that these will probably be *new* rows, but to make this
    # idempotent, we'll look for a match on the date.
    carbs = get_carbs(conn, source, start_time)
    n = len(carbs)
    logging.info(f'{n} carbs to migrate since {start_time}')
    for row in carbs:
        # note: carb_id is called carbohydrate_id in the source
        (user_id, carb_id, date, value) = row
        # see if carb_id matches, to avoid re-inserting something already migrated
        curs.execute(f'''select loop_summary_id, user_id, carb_id
                        from {dest}.loop_summary
                        where user_id = %s and carb_id = %s''',
                     [user_id, carb_id])
        match = curs.fetchone()
        if match is None:
            # First see if there's a CGM at this time
            (cgm_id, cgm_value) = matching_cgm(conn, dest, date)
            # the normal case, we'll look for a bolus row and update that 

            if bolus_row is None:
                pass
            else:
                bolus_id, user
            curs.execute(f'''insert into {dest}.loop_summary
                             (user_id, carb_id, carb_value, linked_cgm_id, linked_cgm_value)
                            values(%s, %s, %s, %s, %s)''',
                         [user_id, carb_id, value, cgm_id, cgm_value])
        else:
            # already exists, so update? Ignore? We'll complain if they differ
            logging.info('carb match: this carb is already migrated: {}'.format(row))
    if commit:
        conn.commit()
        

def re_migrate_carbs(conn, source, dest, start_time, commit=True):
    # nonce when I added the carb_value field. Want to re-migrate all those
    # ran this again when carbs changed from int to double. 2/24/2023
    # ran this yet again when I added a carb_timestamp field. 3/16/2023
    if conn is None:
        conn = dbi.connect()
    curs = dbi.cursor(conn)
    # Note that these will probably be *existing* rows, so we'll look
    # for a match on the date.
    carbs = get_carbs(conn, source, start_time)
    n = len(carbs)
    logging.info(f'{n} carbs to migrate since {start_time}')
    for row in carbs:
        # note: carb_id is called carbohydrate_id in the source
        (user_id, carb_id, date, value) = row
        if value != round(value):
            print('non-int', value, 'at', carb_id)
        # see if carb_id matches, to avoid re-inserting something already migrated
        curs.execute(f'''select loop_summary_id, user_id, carb_id
                        from {dest}.loop_summary
                        where user_id = %s and carb_id = %s''',
                     [user_id, carb_id])
        match = curs.fetchone()
        if match is None:
            # the normal case, we'll insert it. First see if there's a CGM at this time
            (cgm_id, cgm_value) = matching_cgm(conn, dest, date)
            curs.execute(f'''insert into {dest}.loop_summary
                             (user_id, carb_id, carb_timestamp, carb_value, linked_cgm_id, linked_cgm_value)
                            values(%s, %s, %s, %s, %s, %s)''',
                         [user_id, carb_id, date, value, cgm_id, cgm_value])
        else:
            # already exists, so update.
            print('updating', carb_id)
            curs.execute(f'''update {dest}.loop_summary set carb_timestamp = %s where carb_id = %s''',
                         [date, carb_id])
    if commit:
        conn.commit()
    

## ================================================================



def identify_correction_boluses_nonce(conn, source, dest):
    '''one-off function to mark all boluses as either correction or carb.'''
    curs = dbi.cursor(conn)
    nr = curs.execute(f'''select loop_summary_id, bolus_value, bolus_timestamp
                          from {dest}.loop_summary 
                          where bolus_value > 0''')
    print(nr, 'boluses to update')
    n = 0
    carbs = 0
    corrections = 0
    for bolus_row in curs.fetchall():
        id, bolus_value, bolus_timestamp = bolus_row
        some_carbs = carbs_within_interval(conn, source, dest, bolus_timestamp, MATCHING_BOLUS_WITH_CARB_INTERVAL)
        bolus_type = 'carb' if some_carbs else 'correction'
        q = f'''update {dest}.loop_summary set bolus_type = %s where loop_summary_id = %s'''
        curs.execute(q, [bolus_type, id])
        n += 1
        if some_carbs:
            carbs += 1
        else:
            corrections += 1
    print(n, carbs, corrections)
    

        
        
    


## ================================================================
# identify anchor and top-up
# anchor is largest bolus in the last (config) hours
# top-up is latest bolus *after* the anchor, if any.
# set the 'anchor' field: 1=anchor, 2=top-up
# look in dest.configuration to find interval: bolus_interval_minutes

def argmax(seq, func):
    '''Return the element of seq for which func is largest. Returns None
if seq is empty.'''
    if len(seq) == 0:
        return None
    best = seq[0]
    best_val = func(best)
    for elt in seq:
        elt_val = func(elt)
        if elt_val > best_val:
            best, best_val = elt, elt_val
    return best

def identify_anchor_bolus(conn, source, dest, start_time, commit=True):
    '''Identify anchor and topup boluses in the N minutes preceding
start_time, where N is a configuration variable:
bolus_interval_minutes. Only consults dest; source is ignored.
Anchor is largest. top-up is most recent (latest) after the anchor.

Note on 3/16: only correction boluses count.

5/25 as a practical matter, this code will run when a bolus is
identified as a correction, which will mean its the newest bolus in
the table, so this will always be searching back 120 minutes from now. 

    '''
    curs = dbi.cursor(conn)
    curs.execute(f'select bolus_interval_mins from {dest}.configuration')
    interval = curs.fetchone()[0]
    past = date_ui.to_datetime(start_time) - timedelta(minutes=interval)
    # get all boluses in last interval.  We need to check that they
    # are before start_time because we might identify historical
    # anchor_boluses. In practice, start_time==now and the test will
    # be vacuous
    curs.execute(f'''SELECT loop_summary_id,bolus_value,bolus_timestamp 
                     FROM {dest}.loop_summary 
                     WHERE bolus_type = 'correction' 
                        AND bolus_value > 0 
                        AND bolus_timestamp > %s 
                        AND bolus_timestamp <= %s''',
                 [past, start_time])
    rows = curs.fetchall()
    if len(rows) == 0:
        # no anchor because no boluses
        logging.info(f'no boluses in last {interval} minutes from {start_time}')
        return
    # find largest
    anchor_row = argmax(rows, lambda r: r[1])
    logging.info(f'anchor bolus of {anchor_row[1]} at time {anchor_row[2]} ')
    curs.execute(f'update {dest}.loop_summary set anchor=1 where loop_summary_id = %s',
                 [anchor_row[0]])
    if commit:
        conn.commit()
    # Now, look for top-up, latest after. 
    anchor_index = rows.index(anchor_row)
    if anchor_index < len(rows)-1:
        # there are rows *after* the anchor, so latest is the top-up
        topup_row = rows[-1]
        logging.info(f'top-up bolus of {topup_row[1]} at time {topup_row[2]}')
        curs.execute(f'update {dest}.loop_summary set anchor=2 where loop_summary_id = %s',
                     [topup_row[0]])

## Used to test whether identify_anchor_bolus is going to get an error

def identify_anchor_bolus_all(conn, source, dest, start_time, end_time, commit=True):
    st = date_ui.to_datetime(start_time)
    et = date_ui.to_datetime(end_time)
    while st < et:
        identify_anchor_bolus(conn, source, dest, st, commit)
        st += timedelta(minutes=5)


## ================================================================

def read_command_migration_minutes(conn, dest):
    '''Read the command_timeout_mins from the configuration variables and return that; 
if none, use 40 minutes.'''
    curs = dbi.cursor(conn)
    curs.execute(f'''select command_timeout_mins from {dest}.configuration where user_id = %s''',
                 [HUGH_USER_ID])
    rows = curs.fetchall()
    if len(rows) > 1:
        raise Exception('multiple configurations; which do you want', rows)
    if len(rows) == 0:
        return 40
    else:
        return rows[0][0]


def migrate_all(conn, source, dest, alt_start_time=None, test=False):
    '''This is the function that should, eventually, be called from a cron
job every 5 minutes.  If alt_start_time is supplied, ignore the value
from the get_migration_time() table. Uses two start times:
start_time_commands and start_time other.

    '''
    if conn is None:
        conn = dbi.connect()
    logging.info(f'starting migrate_all from {source} to {dest}')
    logging.info('1. realtime cgm')
    # Change on 5/12. We are migrating latest data from realtime_cgm2 *including* the nulls.
    # cancel that; we are only migrating non-null values.
    migrate_cgm_updates(conn, dest)
    # migrate_cgm_updates_with_nulls(conn, dest)
    ## obsolete to use last update? or maybe we should use it if it's later than
    prev_update, last_autoapp_update = get_autoapp_update_times(conn, source, dest)
    cmd_timeout = read_command_migration_minutes(conn, dest)
    start_time_commands = datetime.now() - timedelta(minutes=cmd_timeout)
    start_time_other =  datetime.now() - timedelta(minutes=OTHER_DATA_TIMEOUT)
    if alt_start_time is not None:
        start_time_commands = alt_start_time
        start_time_other = alt_start_time
    elif prev_update is not None:
        # use whichever is later
        start_time_commands = max(prev_update, start_time_commands)
        start_time_other = max(prev_update, start_time_other)
    else:
        # if prev_update is None, that means there's no new data in autoapp
        # since we last migrated, so save ourselves some work by giving up now
        logging.info('no new autoapp data, so giving up')
        return
    logging.info(f'migrating commands since {start_time_commands} and other since {start_time_other}')
    logging.info('2. bolus')
    migrate_boluses(conn, source, dest, start_time_other)
    logging.info('3. commands')
    migrate_commands(conn, source, dest, start_time_commands)
    logging.info('4. carbs')
    migrate_carbs(conn, source, dest, start_time_other)
    if test or alt_start_time:
        logging.info('done, but test mode/alt start time, so not storing update time')
    else:
        logging.info('done. storing update time')
        set_autoapp_migration_time(conn, dest, prev_update, last_autoapp_update)
    logging.info('done')


# ================================================================
# testing this code

''' there are lots of little tests above, but it's hard to test
something that runs the way this does. I'm going to create databases
autoapp_scott and loop_logic_scott with tables like the originals, but
empty. This code empties them out, then successively adds data to
them, and then runs the migration function. 

See sql/scott_setup.sql for the setup of the tables.

If I also use the testing_command table, I can put the cgm values in
loop_logic_scott.source_cgm. But that means I have to use lots of
functions from loop_logic_testing_cgm_cron (lltcc).

Tables the code above uses:

{source}.dana_history_timestamp (for command migration)
{dest}.migration_status (for last command migration)
{dest}.testing_command (to turn on a test)
{dest}.source_cgm (for the cgm values)
{dest}.realtime_cgm (to find the matching cgm values)
{source}.bolus (for bolus data)
{dest}.loop_summary (where everything goes)
{source}.commmands
{source}.commmands_single_bolus_data
{source}.commmands_temporarary_basal_data
{source}.carbohydrate (for carbs to migrate)
{dest}.configuration (to read config params)

That's it!

'''

def test_clear_scott_db_and_start(conn):
    curs = dbi.cursor(conn)
    dest = 'loop_logic_scott'
    source = 'autoapp_scott'
    curs.execute(f'delete from {dest}.loop_summary')
    curs.execute(f'delete from {dest}.realtime_cgm')
    curs.execute(f'delete from {source}.bolus')
    curs.execute(f'delete from {source}.carbohydrate')
    curs.execute(f'delete from {source}.commands_single_bolus_data')
    curs.execute(f'delete from {source}.commands_temporary_basal_data')
    curs.execute(f'delete from {source}.commands')
    curs.execute(f'delete from {dest}.source_cgm')
    curs.execute(f'delete from {dest}.testing_command')
    conn.commit();

def init_cgm(conn, start):
    print('init_cgm')
    curs = dbi.cursor(conn)
    dest = 'loop_logic_scott'
    source = 'autoapp_scott'
    curs.execute(f'delete from {dest}.testing_command')
    curs.execute(f"insert into {dest}.testing_command values (1, 'start', 'on', %s, 'testing migration')",
                 [start])
    conn.commit()
    # a few test cgm values
    for mins in range(0, 100, 5):
        dt = start + timedelta(minutes=mins)
        # we'll use 100+mins for mgdl
        curs.execute(f"insert into {dest}.source_cgm values(7, %s, %s, %s, 1, 1, 'NO')",
                     [dt, dt, 100+mins])
    conn.commit();

def set_data_migration(conn, source, dest, start):
    '''set values saying there's no data (bolus, carbs) prior to 'start'.'''
    # the two tables are initialized with the one row from their sources
    curs = dbi.cursor(conn)
    curs.execute(f'''UPDATE {source}.dana_history_timestamp SET date = %s WHERE user_id = %s''',
                 [start, HUGH_USER_ID])
    # comparison is for < so equality will mean no new data
    curs.execute(f'''UPDATE {dest}.migration_status 
                     SET prev_autoapp_update = %s, prev_autoapp_migration = %s
                    WHERE user_id = %s''',
                 [start, start, HUGH_USER_ID])
    conn.commit()


def test_1():
    '''tests that boluses near carbs are identified as carbs, not corrections'''
    conn = dbi.connect()
    test_clear_scott_db_and_start(conn)
    # times will always be in minutes since the following start
    start = date_ui.to_datetime('2023-05-01 12:00:00')
    dest = 'loop_logic_scott'
    source = 'autoapp_scott'
    set_data_migration(conn, source, dest, start)

    def dt(mins):
        t0 = start + timedelta(minutes=mins)
        return date_ui.str(t0)
    def insert(conn, desc):
        curs = dbi.cursor(conn)
        if desc['table'] == 'bolus':
            # 6 placeholders
            curs.execute(f'insert into autoapp_scott.bolus values(%s, %s, %s, %s, %s, %s, current_timestamp())',
                         desc['vals'])
        elif desc['table'] == 'carbohydrate':
            # 4 placeholders
            curs.execute(f'insert into autoapp_scott.carbohydrate values(%s, %s, %s, %s, current_timestamp())',
                         desc['vals'])
        curs.execute('update autoapp_scott.dana_history_timestamp set date = %s WHERE user_id = %s',
                     [desc['time'], HUGH_USER_ID])
        conn.commit()
        
    USER = 7
    init_cgm(conn, start)
    for data_in in [
            [ {'table': 'bolus', 'time': dt(1), 'vals': [None, USER, dt(1), 'S', 4.0, 0]}, ],
            # this is much later, so previous bolus is correction
            [ {'table': 'carbohydrate', 'time': dt(12), 'vals': [None, USER, dt(12), 40]} ],
            # this is also later, so previous carbs is alone
            [ {'table': 'bolus', 'time': dt(23), 'vals': [None, USER, dt(23), 'S', 5.0, 0]}, ],
            # but this is soon, so will be combined:
            [ {'table': 'carbohydrate', 'time': dt(24), 'vals': [None, USER, dt(24), 50]} ],
            # this pair is much later, carbs first
            [ {'table': 'carbohydrate', 'time': dt(35), 'vals': [None, USER, dt(35), 45]} ],
            [ {'table': 'bolus', 'time': dt(36), 'vals': [None, USER, dt(36), 'S', 4.5, 0]}, ]
            ]:
        for data1_in in data_in:
            print('data in', data1_in)
            # insert data into chosen table
            insert(conn, data1_in)
            # migrate test cgm
            lltcc.cron_copy(conn, 'loop_logic_scott', True)
            # migrate data at test time
            migrate_all(conn, 'autoapp_scott', 'loop_logic_scott', data1_in['time'])
            curs = dbi.cursor(conn)
            curs.execute('''select loop_summary_id, 
                                   bolus_pump_id, time(bolus_timestamp), bolus_type, bolus_value, anchor
                                   carb_id, time(carb_timestamp), carb_value
                            from loop_logic_scott.loop_summary''')
            print('after', data_in)
            print_results(curs.fetchall())

def test_2():
    '''checks that boluses are properly identified as anchor and/or top-up.'''
    conn = dbi.connect()
    test_clear_scott_db_and_start(conn)
    # times will always be in minutes since the following start
    start = date_ui.to_datetime('2023-05-01 12:00:00')
    dest = 'loop_logic_scott'
    source = 'autoapp_scott'
    set_data_migration(conn, source, dest, start)

    def dt(mins):
        t0 = start + timedelta(minutes=mins)
        return date_ui.str(t0)
    def insert(conn, desc):
        curs = dbi.cursor(conn)
        if desc['table'] == 'bolus':
            # 6 placeholders
            curs.execute(f'insert into autoapp_scott.bolus values(%s, %s, %s, %s, %s, %s, current_timestamp())',
                         desc['vals'])
        elif desc['table'] == 'carbohydrate':
            # 4 placeholders
            curs.execute(f'insert into autoapp_scott.carbohydrate values(%s, %s, %s, %s, current_timestamp())',
                         desc['vals'])
        curs.execute('update autoapp_scott.dana_history_timestamp set date = %s WHERE user_id = %s',
                     [desc['time'], HUGH_USER_ID])
        conn.commit()
        
    USER = 7
    init_cgm(conn, start)
    for data_in in [
            # carbs and bolus at the same time, so carbs
            [ {'table': 'carbohydrate', 'time': dt(1), 'vals': [None, USER, dt(1), 40]},
              {'table': 'bolus', 'time': dt(1), 'vals': [None, USER, dt(1), 'S', 4.0, 0]} ],
            # this is later and alone, so a correction. Should be marked as anchor
            [ {'table': 'bolus', 'time': dt(23), 'vals': [None, USER, dt(23), 'S', 5.0, 0]}, ],
            # this is much later and alone, so a correction, but smaller than preceding.
            # Should be marked as top-up
            [ {'table': 'bolus', 'time': dt(80), 'vals': [None, USER, dt(80), 'S', 3.0, 0]}, ],
            # Here's another bolus, that will be briefly considered an anchor, but then changes to carbs
            [ {'table': 'bolus', 'time': dt(120), 'vals': [None, USER, dt(120), 'S', 3.0, 0]}, ],
            [ {'table': 'carbohydrate', 'time': dt(121), 'vals': [None, USER, dt(121), 50]} ],
            ]:
        for data1_in in data_in:
            print('data in', data1_in)
            # insert data into chosen table
            insert(conn, data1_in)
            # migrate test cgm
            lltcc.cron_copy(conn, 'loop_logic_scott', True)
            # migrate data at test time
            migrate_all(conn, 'autoapp_scott', 'loop_logic_scott', data1_in['time'])
            curs = dbi.cursor(conn)
            curs.execute('''select loop_summary_id, 
                                   bolus_pump_id, time(bolus_timestamp), bolus_type, bolus_value, anchor
                                   carb_id, time(carb_timestamp), carb_value
                            from loop_logic_scott.loop_summary''')
            print('after', data_in)
            print_results(curs.fetchall())

def print_results(row_list):
    for row in row_list:
        print('\t'+'\t'.join([str(x) for x in row]))
        


if __name__ == '__main__': 
    conn = dbi.connect()
    # we use this when we've cleared out the database and started again
    if len(sys.argv) > 1 and sys.argv[1] == 'migrate_cgm':
        alt_start_time = sys.argv[2]
        debugging()
        migrate_cgm(conn, 'loop_logic', alt_start_time, True)
        migrate_cgm(conn, 'loop_logic_test', alt_start_time, True)
        # set_cgm_migration_time(conn, alt_start_time, alt_start_time)
        sys.exit()
    if len(sys.argv) > 1 and sys.argv[1] == 'all':
        alt_start_time = sys.argv[2]
        print(f'test migrate_all starting at {alt_start_time}')
        debugging()
        migrate_all(conn, 'autoapp', 'loop_logic', alt_start_time, True)
        sys.exit()
    # The default is to run as a cron job
    # when run as a script, log to a logfile 
    today = datetime.today()
    logfile = os.path.join(LOG_DIR, 'day'+str(today.day))
    now = datetime.now()
    if now.hour == 0 and now.minute==0:
        try:
            os.unlink(logfile)
        except FileNotFound:
            pass
    logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s',
                        datefmt='%H:%M',
                        filename=logfile,
                        level=logging.DEBUG)
    if now.hour == 0 and now.minute==0:
        logging.info('================ first run of the day!!'+str(now))
    logging.info('running at {}'.format(datetime.now()))
    migrate_all(conn, 'autoapp', 'loop_logic')
    migrate_all(conn, 'autoapp_test', 'loop_logic_test')
