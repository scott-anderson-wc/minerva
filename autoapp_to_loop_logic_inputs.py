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

Nov 14, 2023. New version (in a renamed file) that focuses on the
inputs (boluses, carbs, temp_basals) and omits the commands.

The Anchor Bolus (anchor==1) is the largest *correction* bolus in the
given interval.

The Top-up Bolus (anchor==2) is the most recent *correction* bolus
after the Anchor Bolus.

The Carb Bolus (anchor==3) is the largest *carb* bolus in the given
interval.

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

# Global variables used in logging

logstream = None
loghandler = None

HUGH_USER = 'Hugh'
HUGH_USER_ID = 7
MATCHING_BOLUS_INTERVAL = 5    # minutes between command and bolus to match them.
OTHER_DATA_TIMEOUT = 6*60       # minutes to look back for non-command (bolus, carbs)
MATCHING_BOLUS_WITH_CARB_INTERVAL = 20 # minutes between bolus and carbs to match them and put them in a single loop_summary entry. 

'''Changed to 20 from 30 on 7/11/2023. on 10/14/2023, no longer used
to look for carbs; replaced by the following. Still used for matching
bolus with carbs.'''

# if there are carbs in this interval around a bolus, it's a carbs bolus
# 11/14/2023, these were reversed.
CARBS_MINUTES_BEFORE_BOLUS = 20
CARBS_MINUTES_AFTER_BOLUS = 5


# the time in minutes for two timestamps to "match"
TIMEDELTA_MINS = 5

def debugging():
    '''Run this in the Python REPL to turn on debug logging. The default is just error'''
    logging.basicConfig(level=logging.DEBUG)

# ================================================================

'''When we start a run, we stored the time and the value
'starting'. When we end a run normally (without raising an exception
and crashing), we store the final status. If the value says
'starting', we can assume the most recent run resulted in a crash (or
we happen to be looking at the table during the few seconds that the
migration code is running). Otherwise, the final value should be accurate.

Aug 11, 2023
'''

def start_run(conn, source, dest, user_id):
    curs = dbi.cursor(conn)
    curs.execute(f'''UPDATE {dest}.migration_status
                     SET last_run = now(), last_status = 'starting'
                     WHERE user_id = %s''',
                 [user_id])
    conn.commit()

def stop_run(conn, source, dest, user_id, status):
    global logstream
    curs = dbi.cursor(conn)
    curs.execute(f'''UPDATE {dest}.migration_status
                     SET last_run = now(), last_status = %s
                     WHERE user_id = %s''',
                 [status, user_id])
    conn.commit()
    if logstream is not None:
        logstream.close()

# ================================================================

# this is copied from dexcom_cgm_sample.py
# we should consider storing this useful value

def get_latest_stored_data(conn, source):
    '''Looks up the latest data that we stored from previous inquiries.
Returns rtime and dexcom_time from last non-NULL value. We can infer
the number of values we need from Dexcom from those.

Nov 18, we now have a source argument which is either 'dexcom' or 'libre'    

    '''
    curs = dbi.cursor(conn)
    if source == 'dexcom':
        curs.execute('''SELECT rtime, dexcom_time
                        FROM janice.realtime_cgm2
                        WHERE user_id = %s and
                              rtime = (SELECT max(rtime) FROM janice.realtime_cgm2
                                       WHERE user_id = %s and mgdl is not NULL)''',
                     [HUGH_USER_ID, HUGH_USER_ID])
    elif source == 'libre':
        curs.execute('''SELECT rtime, libre_time
                        FROM janice.realtime_cgm_libre
                        WHERE user_id = %s and
                              rtime = (SELECT max(rtime) FROM janice.realtime_cgm_libre
                                       WHERE user_id = %s and mgdl is not NULL)''',
                     [HUGH_USER_ID, HUGH_USER_ID])
    else:
        raise Exception(f'bad value for source: {source}')
    row = curs.fetchone()
    return row



def get_cgm_update_times(conn, source, dest):
    '''Long discussion about the data to migrate. See
https://docs.google.com/document/d/1ZCtErlxRQmPUz_vbfLXdg7ap2hIz5g9Lubtog8ZqFys/edit#heading=h.umdjcuqs1gq4

This function also looks in the janice.realtime_cgm2 table and finds
the most recent value where mgdl is not None (Y). We should probably
store that useful value somewhere. It also returns the prior value of
that, we stored as DEST.migration_status.prev_cgm_update
(PY). Returns both (Y,PY) if Y > Py, otherwise None, None.

A return value of None, None will skip migration of CGM.    

Nov 18, we now have a source argument which is either 'dexcom' or 'libre'    

    '''
    (rtime, cgm_time) = get_latest_stored_data(conn, source)
    last_cgm = min(rtime, cgm_time)
    curs = dbi.cursor(conn)
    curs.execute(f'''select prev_cgm_update from {dest}.migration_status where user_id = %s''',
                 [HUGH_USER_ID])
    prev_cgm = curs.fetchone()[0]
    logging.debug(f'last update from {source} was at {last_cgm}; the previous value was {prev_cgm}')
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
        logging.debug(f'new data in {source} since last migration, so migrate from {prev_autoapp} to {last_autoapp_update}')
        return prev_autoapp, last_autoapp_update # increasing order
    else:
        logging.debug(f'no new data in {source} since last migration')
        return None, None

def set_autoapp_migration_time(conn, dest, prev_update, last_update):
    '''Long discussion about the data to migrate. See
https://docs.google.com/document/d/1ZCtErlxRQmPUz_vbfLXdg7ap2hIz5g9Lubtog8ZqFys/edit#heading=h.umdjcuqs1gq4

This function sets the value of prev_autoapp_update in the
loop_logic.migration_status table to the time of the latest real data
in autoapp.dana_history_timestamp

It uses the passed-in values, to avoid issues of simultaneous updates.

    '''
    logging.debug(f'setting prev {prev_update} and last to current_timestamp')
    curs = dbi.cursor(conn)
    curs.execute(f'''UPDATE {dest}.migration_status 
                    SET prev_autoapp_update = %s, prev_autoapp_migration = current_timestamp() 
                    WHERE user_id = %s''',
                 # notice this says last_ not prev_; we ignore prev here
                 [last_update, HUGH_USER_ID])
    conn.commit()
    return 'done'


# ================================================================

def cgm_source(conn):
    '''Returns either 'dexcom' or 'libre' depending on which sensor is
    currently supplying the data.'''
    curs = dbi.cursor(conn)
    curs.execute('select cgm_source from janice.controls')
    row = curs.fetchone()
    if row is not None:
        return row[0]
    else:
        # default
        return 'dexcom'

def migrate_cgm(conn, dest, start_time, commit=True):
    '''start_time is a string or a python datetime. '''
    if conn is None:
        conn = dbi.connect()
    curs = dbi.cursor(conn)
    source = cgm_source(conn)
    logging.debug(f'migrating realtime_cgm from {source} since {start_time}')
    if source == 'dexcom':
        # must use rtime, not dexcom_time, since the latter can be null
        # but we retrieve the dexcom_time, to be be consistent with {dest}.realtime_cgm
        nrows = curs.execute('''select user_id, dexcom_time, mgdl, trend, trend_code
                                from janice.realtime_cgm2
                                where rtime > %s and mgdl is not NULL''',
                             [start_time])
    elif source == 'libre':
        # New query for realtime_cgm_libre, setting trend_code to NULL
        nrows = curs.execute('''select user_id, libre_time as dexcom_time, mgdl, trend, NULL as trend_code
                                from janice.realtime_cgm_libre
                                where rtime > %s and mgdl is not NULL''',
                             [start_time])
    else:
        raise ValueError(f'''bad value returned from 'cgm_source': {source}''')
    logging.debug(f'got {nrows} from realtime_cgm2 from source {source}')
    ins = dbi.cursor(conn)
    for row in curs.fetchall():
        # we can't use on duplicate key, because the key is an auto_increment value that we don't have.
        # So we have to look for matches on timestamp values. 
        (user_id, dexcom_time, _, _, _) = row
        nr = ins.execute(f'''select cgm_id from {dest}.realtime_cgm 
                             where user_id = %s and dexcom_time = %s''',
                         [user_id, dexcom_time])
        logging.debug(f'found {nr} matches (already migrated rows) for time {dexcom_time}')
        if nr == 0:
            logging.debug(f'inserting into {dest}.realtime_cgm cgm = {row[2]} from {source}')
            if source == 'dexcom':
                ins.execute(f'''insert into {dest}.realtime_cgm(cgm_id,user_id,dexcom_time,mgdl,trend,trend_code,src)
                                values(null,%s,%s,%s,%s,%s,'dexcom')''',
                            row)
            elif source == 'libre':
                # Updated insertion with trend_code set to NULL
                ins.execute(f'''insert into {dest}.realtime_cgm(cgm_id,user_id,dexcom_time,mgdl,trend,trend_code,src)
                                values(null,%s,%s,%s,%s,NULL,'libre')''',
                            (user_id, dexcom_time, row[2], row[3]))  # omitting trend_code
                    
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
    source = cgm_source(conn)
    prev_cgm_update, last_cgm_update = get_cgm_update_times(conn, source, dest)
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
    # why are we fetching the user_id?
    curs.execute(f'''select user_id, bolus_id, date, value 
                    from {source}.bolus
                    where date >= %s''',
                 [start_time])
    return curs.fetchall()
    
def carbs_within_interval_without_bolus(conn, source, dest, timestamp,
                                        mins_before=CARBS_MINUTES_BEFORE_BOLUS,
                                        mins_after=CARBS_MINUTES_AFTER_BOLUS):
    '''returns loop_summary_id, carb_id, carb_timestamp, carb_value
searching for carb value in loop_summary given minutes before or after
timestamp. The carbs are *not* already matched with a bolus. Returns
None if no match.

    '''
    if conn is None:
        conn = dbi.connect()
    curs = dbi.cursor(conn)
    # TODO: this will be O(n) unless we build an index on carb_timestamp
    # or search based on the NYI loop_summary timestamp.
    nr = curs.execute(f'''SELECT loop_summary_id, carb_id, carb_timestamp, carb_value 
                          FROM {dest}.loop_summary 
                          WHERE user_id = %s  
                          AND bolus_pump_id is NULL
                          AND carb_timestamp 
                          BETWEEN (%s - interval %s minute) 
                              AND (%s + interval %s minute)''',
                 [HUGH_USER_ID, timestamp, mins_before, timestamp, mins_after])
    rows = curs.fetchall()
    # hopefully the normal case
    if nr == 1:
        return rows[0]
    if nr == 0:
        logging.debug(f'no carbs w/o bolus in interval around {timestamp}')
        return None
    if nr > 1:
        logging.debug(f'multiple carbs in interval around {timestamp}; using largest')
        biggest = argmax(rows, lambda r: r[3])
        return biggest

def carbs_within_interval_test(conn, source, dest, start_time):
    '''This is for basic robustness and correctness. Modifies no data, so safe to use in any database.'''
    if conn is None:
        conn = dbi.connect()
    curs = dbi.cursor(conn)
    for bolus_row in get_boluses(conn, source, start_time):
        (user_id, bolus_pump_id, bolus_time, value) = bolus_row
        match = carbs_within_interval(conn, source, dest, bolus_time)
        if match is None:
            print(f'correction bolus at {bolus_time}')
        else:
            (id, carb_id, carb_time, carb_value) = match
            if (carb_time < bolus_time - timedelta(minutes=CARBS_MINUTES_BEFORE_BOLUS) or
                carb_time > bolus_time + timedelta(minutes=CARBS_MINUTES_AFTER_BOLUS)):
                print(f'ERROR at {bolus_time}')
                print(f'{id}, {carb_id}, {carb_time}, {carb_value}')
                raise Exception
            print(f'loop summary id {id} for carb_id {carb_id} matches')
        
def migrate_boluses(conn, source, dest, start_time, commit=True):
    '''start_time is a string or a python datetime. '''
    if conn is None:
        conn = dbi.connect()
    curs = dbi.cursor(conn)
    # Note that these will probably be *new* rows, but to make this
    # idempotent, we'll look for a bolus_id
    # This function returns a list of tuples: user_id, bolus_id, date, value 
    boluses = get_boluses(conn, source, start_time)
    n = len(boluses)
    logging.info(f'{n} boluses to migrate since {start_time}')
    for row in boluses:
        # note: bolus_id is called bolus_pump_id in loop_logic
        (user_id, bolus_pump_id, date, value) = row
        logging.debug(f'migrate bolus_pump_id={bolus_pump_id} on date {date} of value {value}')
        # see if bolus_pump_id matches, to avoid re-inserting
        # something already migrated TODO: for speed, we either need
        # an index on bolus_pump_id (good) or use the bolus_timestamp
        # and have an index on the time stamp of the loop_summary
        # entry, which we don't have (yet). Maybe we should?
        curs.execute(f'''select loop_summary_id, user_id, bolus_pump_id, bolus_timestamp, bolus_value
                        from {dest}.loop_summary
                        where user_id = %s and bolus_pump_id = %s''',
                     [user_id, bolus_pump_id])
        match = curs.fetchone()
        if match is not None:
            # already exists, so update? Ignore? We'll complain if they differ
            match_id = match[0]
            logging.info(f'bolus match: this bolus is already migrated: see {dest}.loop_summary row {match_id}')
            continue
        # the normal case, we'll migrate it (either insert or update an existing row with matching carbs).
        # First see if there's a CGM at this time
        (cgm_id, mgdl) = matching_cgm(conn, dest, date)
        # next, see if there are carbs w/in an interval. if so, update that row
        # 5/19. Get info about the carbs, to fill into loop_summary fields
        carb_row = carbs_within_interval_without_bolus(conn, source, dest, date)
        if carb_row is None:
            logging.debug(f'CASE C: migrate bolus at time {date} has no matching carbs')
            # have to insert into loop_summary
            bolus_type = 'correction' # since no carbs
            curs.execute(f'''INSERT INTO {dest}.loop_summary
                             (user_id, bolus_pump_id, bolus_timestamp, bolus_type, bolus_value,
                             linked_cgm_id, linked_cgm_value)
                             values(%s, %s, %s, %s, %s, %s, %s)''',
                         [user_id, bolus_pump_id, date, bolus_type, value, cgm_id, mgdl])
            if commit:
                conn.commit()
            curs.execute('select last_insert_id()');
            loop_summary_id = curs.fetchone()[0]
            logging.debug(f'inserted correction bolus at loop_summary_id {loop_summary_id}')
            compute_correction_anchors(conn, source, dest, start_time, commit)
            # for debugging
            curs.execute(f'select anchor from {dest}.loop_summary where loop_summary_id = %s', [loop_summary_id])
            anchor = curs.fetchone()[0]
            if anchor not in [1, 2]:
                logging.error(f'inserted a new correction bolus at {loop_summary_id} but anchor type is not 1 or 2!!!')
        else:
            # since there are matching carbs, update that row instead
            # we actually don't need the other data, since it's already in the row
            (loop_summary_id, carb_id, carb_timestamp, carb_value) = carb_row
            logging.debug(f'CASE D: migrate bolus at time {date} has matching carbs {carb_value} at time {carb_timestamp}')
            bolus_type = 'carb'
            # let's compute the carb anchor now.
            anchor_value = compute_carb_anchor(conn, source, dest, value, loop_summary_id, start_time)
            if anchor_value not in [None, 3]:
                logging.error(f'loop summary {loop_summary_id} updated with a carb bolus, but anchor is not None or 3')
            curs.execute(f'''UPDATE {dest}.loop_summary
                             SET bolus_pump_id = %s, bolus_timestamp = %s, bolus_type = %s, bolus_value = %s,
                                 anchor = %s,
                                 linked_cgm_id = %s, linked_cgm_value = %s
                             WHERE loop_summary_id = %s''',
                         [bolus_pump_id, date, bolus_type, value, anchor_value, cgm_id, mgdl, loop_summary_id])
            if commit:
                conn.commit()
    
def migrate_boluses_test(conn, source, dest, start_time, commit=True):
    curs = dbi.cursor(conn)
    nr = curs.execute('''select carb_timestamp from lltt.loop_summary where carb_timestamp is not null''')
    print(f'{nr} carbs for testing')
    carb_times = [r[0] for r in curs.fetchall()]
    migrate_boluses(conn, source, 'lltt', start_time, commit=commit)

## ================================================================

def get_latest_temp_basal_since_time(conn, source, user_id, start_time):
    '''Return the most recent temp basal (anything after start_time) as a
tuple, or None. We only need to look at the temp_basal_state table,
since we just want temp_basal_in_progress (1 or 0), date, and
temp_basal_percent. 

Janice said we only need the latest, so just look for max ID, so this
returns one tuple or None.

The Loop Summary Table document
https://docs.google.com/document/d/1q4dZxhWAhJvpTycH-U17Es44d4eqjoIH/edit
says that we only need the latest row and only if
temp_basal_in_progress=1, so that's what I've done. See additional notes in migrate_temp_basal.

    '''
    curs = dbi.cursor(conn)
    curs.execute(f'''select temp_basal_state_id, temp_basal_in_progress, temp_basal_percent, date 
                    from {source}.temp_basal_state
                    where temp_basal_state_id = (select max(temp_basal_state_id) 
                                             from {source}.temp_basal_state
                                             where user_id = %s and error = 0 and date >= %s)
                    ''',
                 [user_id, start_time])
    return curs.fetchone()

def migrate_temp_basal(conn, source, dest, user_id, start_time, commit=True):
    '''start_time is a string or a python datetime.  Migrating temp basal
is fairly easy: we look for any non-error rows later than start_time
and we migrate the latest such row. We migrate both in_progress=0 and
in_progress=1; that way, loop will know both the current state and a
timestamp for it. Note that the temp_basal_state table is not
voluminous. For all of July 2023, there are only 218 non-error rows,
so that's about 7 per day.

We are not sure why there are more rows with in_progress=0 versus
in_progress=1.

    '''
    if conn is None:
        conn = dbi.connect()
    curs = dbi.cursor(conn)
    basal = get_latest_temp_basal_since_time(conn, source, user_id, start_time)
    if basal is None:
        logging.info(f'no temp basal in {source} to migrate since {start_time}')
        return
    (id, in_progress, percent, date) = basal
    in_progress = bytes_to_int(in_progress)
    logging.info(f'migrating temp basal {id}: in_progress: {in_progress}, {percent}% at {date} > {start_time}')
    # TODO: this needs the user_id
    # Check back to https://docs.google.com/document/d/1q4dZxhWAhJvpTycH-U17Es44d4eqjoIH/edit
    # which says to set command_id to NULL and type='temporary_basal'
    (cgm_id, mgdl) = matching_cgm(conn, dest, date)
    # have to insert into loop_summary
    curs.execute(f'''INSERT INTO {dest}.loop_summary
                     (user_id, command_id, type, temp_basal_timestamp, temp_basal_percent, running,
                      linked_cgm_id, linked_cgm_value)
                     VALUES(%s, NULL, 'temporary_basal', %s, %s, %s, %s, %s)''',
                 [user_id, date, percent, in_progress, cgm_id, mgdl])
    if commit:
        conn.commit()

## ================================================================

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


def matching_bolus_row_within(conn, source, bolus_amount, timestamp, interval_minutes=30):
    '''Returns the row (as a dictionary) from the `autoapp.bolus` table
    with given bolus amount closest in time to the given timestamp and
    within the given interval.  While it's possible to do the query
    entirely in the database, I'm not sure it's worth it. The query is
    very complex and it's almost certainly easier to fetch the 12 rows
    around the timestamp to Python and find the best match, if any,
    here. So, that's what I've done.

    '''
    curs = dbi.dict_cursor(conn)
    query = f'''SELECT bolus_id, user_id, date, type, value, duration, server_date 
               FROM {source}.bolus
               WHERE user_id = %s 
                 AND value = %s
                 AND date between (%s - interval %s minute) AND (%s + interval %s minute)
            '''
    nr = curs.execute(query, [HUGH_USER_ID,
                              bolus_amount,
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

def remove_cancel_temporary_basal(rows):
    '''iterate over rows in pairs, removing cancel_temporary_basal
commands that are immediately followed by a temporary_basal command
with the same timestamp. Rows are lists of the form 
[command_id, user_id, created_timestamp, type...]'''
    if len(rows) < 2:
        return rows
    results = []
    prev = [None, None, None, None]
    for curr in rows:
        (_, _, pct, ptype,*_) = prev
        (_, _, cct, ctype,*_) = curr
        if pct == cct and ptype == 'cancel_temporary_basal' and ctype == 'temporary_basal':
            results.pop()       # remove previous command
        results.append(curr)
        prev = curr
    return results

def remove_cancel_temporary_basal_test():
    CAN='cancel_temporary_basal'
    TMP='temporary_basal'
    return remove_cancel_temporary_basal(
        [ [1,7,1,CAN],
          [2,7,1,TMP],
          [3,7,3,CAN],
          [4,7,3,TMP],
          [5,7,5,CAN],
          ])

def remove_repeats(rows):
    '''iterate over rows in pairs, removing repeats. so [1,2,2,3,3,4] => [1,2,3,4]'''
    if len(rows) < 2:
        return rows
    ## This algorithm skips the second of a pair, while the previous
    ## algorithm removes the first of a pair.
    results = []
    prev = None
    for curr in rows:
        if curr == prev:
            continue
        results.append(curr)
        prev = curr
    return results

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

def bolus_within_interval_without_carbs(conn, source, dest, timestamp,
                                        mins_before=CARBS_MINUTES_AFTER_BOLUS,
                                        mins_after=CARBS_MINUTES_BEFORE_BOLUS):
    '''returns loop_summary_id, bolus_pump_id, bolus_timestamp, bolus_value searching for bolus in loop_summary within the given
time range of timestamp. Returns None if no match.

    '''
    if conn is None:
        conn = dbi.connect()
    curs = dbi.cursor(conn)
    nr = curs.execute(f'''SELECT loop_summary_id, bolus_pump_id, bolus_timestamp, bolus_value 
                          FROM {dest}.loop_summary 
                          WHERE user_id = %s  
                          AND carb_id IS NULL
                          AND bolus_pump_id IS NOT NULL
                          AND bolus_timestamp 
                          BETWEEN (%s - interval %s minute) 
                              AND (%s + interval %s minute)''',
                 [HUGH_USER_ID, timestamp, mins_before, timestamp, mins_after])
    rows = curs.fetchall()
    # hopefully the normal case
    if nr == 1:
        return rows[0]
    if nr == 0:
        # this is also normal
        logging.debug(f'no bolus w/o carbs in from {timestamp} - {mins_before} to + {mins_after}')
        return None
    if nr > 1:
        logging.debug(f'multiple boluses w/o carbs in interval around {timestamp}; using largest')
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
        # TODO: check the efficiency of this query
        curs.execute(f'''select loop_summary_id, user_id, carb_id
                        from {dest}.loop_summary
                        where user_id = %s and carb_id = %s''',
                     [user_id, carb_id])
        match = curs.fetchone()
        if match is not None:
            # already exists, so update? Ignore? We'll complain if they differ
            logging.info('carb match: this carb is already migrated: {}'.format(row))
            continue
        # no match, so we'll migrate it (either insert or update w/ matching bolus).
        # First see if there's a CGM at this time
        (cgm_id, cgm_value) = matching_cgm(conn, dest, carb_date)
        # 5/23. Get info about a bolus at this time. If so, use that row of loop_summary
        bolus_row = bolus_within_interval_without_carbs(conn, source, dest, carb_date)
        if bolus_row is None:
            curs.execute(f'''INSERT INTO {dest}.loop_summary
                            (user_id, carb_id, carb_timestamp, carb_value, linked_cgm_id, linked_cgm_value)
                            VALUES (%s, %s, %s, %s, %s, %s)''',
                             [user_id, carb_id, carb_date, value, cgm_id, cgm_value])
            curs.execute('select last_insert_id()')
            loop_id = curs.fetchone()[0]
            logging.debug(f'CASE A: new carbs, no matching bolus, inserted {loop_id}')
        else:
            # reuse existing row. Note that this revision means
            # that the bolus is now associated with carbs, so
            # change its type to 'carb' and its anchor to NULL
            # Change on 7/26, anchor might not be NULL; might be 3
            (loop_summary_id, bolus_pump_id, bolus_timestamp, bolus_value) = bolus_row
            logging.debug(f'CASE B. migrate carbs at time {carb_date} has matching bolus {bolus_pump_id} at time {bolus_timestamp} in row {loop_summary_id}')
            bolus_type = 'carb'
            # check for anchor
            anchor = compute_carb_anchor(conn, source, dest, value, loop_summary_id, start_time)
            if anchor not in [None, 3]:
                logging.error(f'loop summary {loop_summary_id} updated with a carb bolus, but anchor is not None or 3')
            curs.execute(f'''UPDATE {dest}.loop_summary
                             SET carb_id = %s, carb_timestamp = %s, carb_value = %s, 
                                 bolus_type = 'carb', anchor = %s,
                                 linked_cgm_id = %s, linked_cgm_value = %s
                             WHERE loop_summary_id = %s''',
                         [carb_id, carb_date, value, anchor, cgm_id, cgm_value, loop_summary_id])
    if commit:
        conn.commit()

def compute_carb_anchor(conn, source, dest, curr_bolus_value, curr_loop_summary_id, start_time, commit=True):
    '''When a bolus switches from correction to carb, we have to compute
whether it's the current anchor. This function looks in the interval
preceding start_time and determines the bolus value and
loop_summary_id of the anchor (largest carb bolus). If the new carb
bolus beats it, we return 3 otherwise None.

    '''
    logging.info(f'determining carb anchor in interval preceding {start_time}')
    curs = dbi.cursor(conn)
    # this was fixed. Had been bolus_interval_minutes.
    curs.execute(f'select carb_interval_mins from {dest}.configuration')
    interval = curs.fetchone()[0]
    past = date_ui.to_datetime(start_time) - timedelta(minutes=interval)
    # get all carb boluses in last interval.  We need to check that
    # they are before start_time because we might identify historical
    # anchor_boluses. In practice, start_time==now and the test will
    # be vacuous
    curs.execute(f'''SELECT loop_summary_id, bolus_type, bolus_value, bolus_timestamp 
                     FROM {dest}.loop_summary 
                     WHERE bolus_type = 'carb' 
                        AND bolus_value > 0 
                        AND bolus_timestamp > %s 
                        AND bolus_timestamp <= %s''',
                 [past, start_time])
    rows = curs.fetchall()
    anchor_row = argmax(rows, lambda r: r[2])
    # since we haven't updated the row yet, it won't be in the
    # rows. If anchor_row is None, curr is the winner. Otherwise, we
    # have to compare.
    if anchor_row is None:
        return 3
    if anchor_row[2] < curr_bolus_value:
        return 3
    return None

def dict_str(d):
    '''Returns a new dictionary with each value converted to a str; nice for printing'''
    try:
        if d is None:
            return None
        return {k: str(v) for k, v in d.items()}
    except Error:
        return 'could not convert to dict with string values'


## ================================================================
# identify anchor and top-up
# anchor is largest bolus in the last (config) hours
# top-up is latest bolus *after* the anchor, if any.
# set the 'anchor' field: 1=anchor, 2=top-up
# look in dest.configuration to find interval: bolus_interval_minutes

def argmax(seq, func):
    '''Return the element of seq for which func is largest. Returns None
if seq is empty. In the event of a tie, returns the last such.'''
    if len(seq) == 0:
        return None
    best = seq[0]
    best_val = func(best)
    for elt in seq:
        elt_val = func(elt)
        try:
            if elt_val >= best_val:
                best, best_val = elt, elt_val
        except:
            logging.error(f'error in argmax comparing {elt_val} with {best_val}')
            return None
    return best

def compute_correction_anchors(conn, source, dest, start_time, commit=True):
    '''Identify anchor and topup boluses in the N minutes preceding
start_time, where N is a configuration variable:
bolus_interval_minutes. Only consults dest; source is ignored.  Anchor
is largest. top-up is most recent (latest) after the anchor.  This
function returns no value; it updates the table, since the anchor and
top-up may change based on new boluses and not just in the current row.

Note on 3/16: only correction boluses count.

5/25 as a practical matter, this code will run when a bolus is
identified as a correction, which will mean its the newest bolus in
the table, so this will always be searching back 120 minutes from now. 

7/26, Janice asked for anchor=3 to be the largest carb bolus within
the interval, so added that. I changed the query to look for all
boluses in the interval, and then I'll filter them here. NO; see next.

11/14 since the time interval is different between correction boluses
and carb boluses, I've separated these computations into two
functions. This is just correction boluses.

    '''
    curs = dbi.cursor(conn)
    curs.execute(f'select bolus_interval_mins from {dest}.configuration')
    interval = curs.fetchone()[0]
    past = date_ui.to_datetime(start_time) - timedelta(minutes=interval)
    # get all correction boluses in last interval.  We need to check that they
    # are before start_time because we might identify historical
    # anchor_boluses. In practice, start_time==now and the test will
    # be vacuous
    curs.execute(f'''SELECT loop_summary_id, bolus_type, bolus_value, bolus_timestamp 
                     FROM {dest}.loop_summary 
                     WHERE bolus_type = 'correction'
                        AND bolus_value > 0 
                        AND bolus_timestamp > %s 
                        AND bolus_timestamp <= %s''',
                 [past, start_time])
    rows = curs.fetchall()
    # print('recent boluses')
    # for r in rows: print(r)
    if len(rows) == 0:
        # no anchor because no boluses
        logging.info(f'no boluses in last {interval} minutes from {start_time}')
        return
    if len(rows) > 0:
        # find largest correction bolus
        anchor_row = argmax(rows, lambda r: r[2])
        logging.info(f'anchor bolus of {anchor_row[1]} at time {anchor_row[2]} ')
        curs.execute(f'update {dest}.loop_summary set anchor=1 where loop_summary_id = %s',
                     [anchor_row[0]])
        # Now, look for top-up, latest after. 
        anchor_index = rows.index(anchor_row)
        if anchor_index < len(rows)-1:
            # there are rows *after* the anchor, so latest is the top-up
            topup_row = rows[-1]
            logging.info(f'top-up bolus of {topup_row[2]} at time {topup_row[3]}')
            curs.execute(f'update {dest}.loop_summary set anchor=2 where loop_summary_id = %s',
                         [topup_row[0]])
    if commit:
        conn.commit()


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

Oct 13, 2023, rearranged the order to migrate commands first. Well,
    second, after the CGM.

    '''
    logfile_start(source)
    if conn is None:
        conn = dbi.connect()
    logging.info(f'starting migrate_all from {source} to {dest}')
    logging.info('1. realtime cgm')
    start_run(conn, source, dest, HUGH_USER_ID)
    # Change on 5/12/2023. We are migrating latest data from realtime_cgm2 *including* the nulls.
    # cancel that; we are only migrating non-null values.
    migrate_cgm_updates(conn, dest)
    ## obsolete to use last update? or maybe we should use it if it's later than
    ## These times are for *data* not commands
    prev_update, last_autoapp_update = get_autoapp_update_times(conn, source, dest)
    logging.debug(f'for {source}, last autoapp data updates are {prev_update} and {last_autoapp_update}')
    if alt_start_time is not None:
        start_time_data = alt_start_time
    else:
        # normally, we check prev_update. If it's None, there's no new data, so do nothing.
        # if it's not None, use the later of prev_update and start_time_data_default
        if prev_update is None:
            logging.info(f'no new data in {source}')
            start_time_data = None
        else:
            start_time_data_default =  datetime.now() - timedelta(minutes=OTHER_DATA_TIMEOUT)
            if prev_update > start_time_data_default:
                # normal case; autoapp is up-to-date
                start_time_data = prev_update
            else:
                logging.debug(f'outage case. migrating from {start_time_data_default}')
                # outage case. autoapp is old. See discussion in Google doc
                # https://docs.google.com/document/d/1ZCtErlxRQmPUz_vbfLXdg7ap2hIz5g9Lubtog8ZqFys/edit#heading=h.ajk7a72eiyjk
                # Use default time, and plan to store current time as prev_update
                start_time_data = start_time_data_default
                prev_update = datetime.now()
    if start_time_data is None:
        logging.debug(f'3. no data to migrate')
    else:
        logging.info(f'3. migrating data since {start_time_data}')
        logging.info(f'3a. migrating bolus since {start_time_data}')
        migrate_boluses(conn, source, dest, start_time_data)
        logging.info(f'3b. migrating temp basal since {start_time_data}')
        migrate_temp_basal(conn, source, dest, HUGH_USER_ID, start_time_data)
        logging.info(f'3c. migrating carbs since {start_time_data}')
        migrate_carbs(conn, source, dest, start_time_data)
        logging.info(f'3d. identifying anchors since {start_time_data}')
    # last, store times for the next run
    if test or alt_start_time:
        logging.info('done, but test mode/alt start time, so not storing update time')
    else:
        # last_autoapp_update is None when there's no data (but there might be commands)
        if last_autoapp_update is not None:
            logging.info(f'done. storing update times {prev_update}, {last_autoapp_update}')
            set_autoapp_migration_time(conn, dest, prev_update, last_autoapp_update)
        else:
            logging.info('done. skip storing data update time, because it is None')
        # always note successful completion
        stop_run(conn, source, dest, HUGH_USER_ID, 'success')


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
    '''tests that boluses near carbs are identified as carbs, not
corrections. Also tests their categorizations as anchors.'''
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
    for scenario, data_in in enumerate([
            # scenario 0, bolus w/o carbs, so correction and anchor=1
            [ {'table': 'bolus', 'time': (1), 'vals': [None, USER, dt(1), 'S', 4.0, 0]}, ],
            # this is much later (> 20 minutes), so previous bolus is still correction and will be anchor=1
            [ {'table': 'carbohydrate', 'time': (32), 'vals': [None, USER, dt(32), 40]} ],
            # this is also later, so previous carbs is alone, and this is a correction bolus and anchor=1
            [ {'table': 'bolus', 'time': (62), 'vals': [None, USER, dt(62), 'S', 5.0, 0]}, ],
            # but these carbs are soon, so will be combined with the bolus at time 62, changing to carbs bolus and anchor=3
            [ {'table': 'carbohydrate', 'time': (64), 'vals': [None, USER, dt(64), 50]} ],
            # this pair is a little later, carbs first. This will be a
            # carbs bolus, and will be the anchor=None, because it's
            # smaller than the previous carb bolus at 64
            [ {'table': 'carbohydrate', 'time': (85), 'vals': [None, USER, dt(85), 45]} ],
            [ {'table': 'bolus', 'time': (86), 'vals': [None, USER, dt(86), 'S', 4.5, 0]}, ],
            # this pair is much later, carbs first. This will be a carbs bolus, and will be the anchor=3
            [ {'table': 'carbohydrate', 'time': (285), 'vals': [None, USER, dt(285), 60]} ],
            [ {'table': 'bolus', 'time': (286), 'vals': [None, USER, dt(286), 'S', 6, 0]}, ],
            # this pair is just a little later than the last pair, but
            # same carb value, so the new row will be the anchor (ties
            # go to the most recent)
            [ {'table': 'carbohydrate', 'time': (305), 'vals': [None, USER, dt(305), 30]} ],
            [ {'table': 'bolus', 'time': (306), 'vals': [None, USER, dt(306), 'S', 6, 0]}, ],
            # two corrections; the second will be a top-up
            [ {'table': 'bolus', 'time': (401), 'vals': [None, USER, dt(401), 'S', 7, 0]}, ],
            [ {'table': 'bolus', 'time': (432), 'vals': [None, USER, dt(432), 'S', 3, 0]}, ],
            
            ]):
        for data1_in in data_in:
            time = data1_in['time']
            local_time = dt(time)
            data1_in['time'] = local_time
            print(f'****************\n scenario {scenario} \n time: {time} == {local_time}\n', data1_in)
            # insert data into chosen table
            insert(conn, data1_in)
            # migrate test cgm
            lltcc.cron_copy(conn, 'loop_logic_scott', True)
            # migrate data at test time
            migrate_all(conn, 'autoapp_scott', 'loop_logic_scott', local_time)
            curs = dbi.cursor(conn)
            curs.execute('''select loop_summary_id, 
                                   bolus_pump_id, time(bolus_timestamp), bolus_type, bolus_value, anchor,
                                   carb_id, time(carb_timestamp), carb_value, '&'
                            from loop_logic_scott.loop_summary''')
            print('after', data_in)
            print_results(curs.fetchall())

'''A test function consists of set of scenarios. Each scenario has a
text description, and a sequence of inputs. Each input might need to
update several tables, so the input is also a list of table
insertions, though usually a list of only one.'''

def test_1a():
    pass

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
            # this is later and alone, so a correction. Should be marked as anchor=1
            [ {'table': 'bolus', 'time': dt(23), 'vals': [None, USER, dt(23), 'S', 5.0, 0]}, ],
            # this is much later and alone, so a correction, but smaller than preceding.
            # Should be marked as top-up (anchor=2)
            [ {'table': 'bolus', 'time': dt(80), 'vals': [None, USER, dt(80), 'S', 3.0, 0]}, ],
            # Here's another bolus, that will be briefly considered an correction, but then changes to carbs
            # will have anchor=3
            [ {'table': 'bolus', 'time': dt(120), 'vals': [None, USER, dt(120), 'S', 3.0, 0]}, ],
            [ {'table': 'carbohydrate', 'time': dt(121), 'vals': [None, USER, dt(121), 50]} ],
            ]:
        for data1_in in data_in:
            print('data in', data1_in, 'time', (date_ui.to_datetime(data1_in['time'])-start).seconds/60)
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

def test_3():
    '''This test is all about merging two different events into a single
loop_summary row. A bolus event and an bolus command, in either order,
results in just one loop_summary row. Similarly, a carbs and a bolus,
in either order, should result in just one loop_summary row. This
function tests those 4 scenarios.

It also checks for a scenario with dinner+dessert, where carbs and
boluses come in quick succession, but we want *two* loop_summary
entries, not one.

It also tests identification of anchors.

    '''
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
            curs.execute(f"insert into autoapp_scott.bolus values(%s, %s, %s, %s, %s, %s, %s)",
                         desc['vals'])
        elif desc['table'] == 'bolus_command':
            # 1 placeholder, though maybe we should allow entering the whole row, as with the others
            curs.execute(f"insert into autoapp_scott.commands(user_id, completed, type, created_timestamp) values(%s, %s, %s, %s)",
                         desc['com_vals'])
            curs.execute('select last_insert_id()')
            comm_id = curs.fetchone()[0]
            curs.execute('insert into autoapp_scott.commands_single_bolus_data values(%s, %s, 99, %s)',
                         [comm_id, desc['amt'], desc['amt']])
            curs.execute('update autoapp_scott.dana_history_timestamp set date = %s WHERE user_id = %s',
                         [desc['time'], HUGH_USER_ID])
        elif desc['table'] == 'carbs':
            curs.execute(f"insert into autoapp_scott.carbohydrate(user_id,date,value) values(%s, %s, %s)",
                         desc['vals'])
        conn.commit()
        
    USER = 7
    init_cgm(conn, start)
    for idx, scenario in enumerate([
            # 3 unit bolus first, command 1 minute later. No carbs, so this is a correction bolus
            [ {'table': 'bolus', 'time': dt(1), 'vals': [None, USER, dt(1), 'S', 3.0, 0, dt(1)]},
              {'table': 'bolus_command', 'time': dt(2), 'com_vals': [USER, 1, 'bolus', dt(2)], 'amt': 3},
             ],
            # command first, 4 unit bolus 1 minute later. Another correction bolus
            [
                {'table': 'bolus_command', 'time': dt(10), 'com_vals': [USER, 1, 'bolus', dt(10)], 'amt': 4},
                {'table': 'bolus', 'time': dt(11), 'vals': [None, USER, dt(11), 'S', 4.0, 0, dt(11)]},
             ],
            # 100 minutes later, 30 carbs first, 5 unit bolus 1 minute later. This is a carb bolus
            [ {'table': 'carbs', 'time': dt(110), 'vals': [USER, dt(110), 30]},
              {'table': 'bolus', 'time': dt(111), 'vals': [None, USER, dt(111), 'S', 5.0, 0, dt(111)]},
             ],
            # another 100 minutes later, 40 carbs second, 6 unit bolus 1 minute earlier
            # note that the carbs needs to update the bolus type to 'carbs'
            [
                {'table': 'bolus', 'time': dt(210), 'vals': [None, USER, dt(210), 'S', 6.0, 0, dt(210)]},
                {'table': 'carbs', 'time': dt(211), 'vals': [USER, dt(211), 40]},
             ],
            # a three-event combo. A carbs bolus
            [
                {'table': 'carbs', 'time': dt(310), 'vals': [USER, dt(310), 50]},
                {'table': 'bolus_command', 'time': dt(311), 'com_vals': [USER, 1, 'bolus', dt(311)], 'amt': 7},
                {'table': 'bolus', 'time': dt(312), 'vals': [None, USER, dt(312), 'S', 7.0, 0, dt(312)]},
             ],
            # three successive boluses with carbs. First is anchor=3, last is top-up
            [
                {'table': 'carbs', 'time': dt(410), 'vals': [USER, dt(410), 50]},
                {'table': 'bolus', 'time': dt(412), 'vals': [None, USER, dt(412), 'S', 7.0, 0, dt(412)]},
                {'table': 'bolus', 'time': dt(422), 'vals': [None, USER, dt(422), 'S', 2.0, 0, dt(422)]},
                {'table': 'bolus', 'time': dt(432), 'vals': [None, USER, dt(432), 'S', 2.0, 0, dt(432)]},
             ],
            # dinner + dessert
            [
                {'table': 'carbs', 'time': dt(601), 'vals': [USER, dt(601), 60]},
                {'table': 'bolus', 'time': dt(602), 'vals': [None, USER, dt(602), 'S', 8.0, 0, dt(602)]},
                {'table': 'carbs', 'time': dt(603), 'vals': [USER, dt(603), 20]},
                {'table': 'bolus', 'time': dt(604), 'vals': [None, USER, dt(604), 'S', 3.0, 0, dt(604)]},
            ],
    ]):
        print(f'==== scenario {idx} ===========')
        for data_in in scenario:
            print('data in', data_in)
            # insert data into chosen table
            insert(conn, data_in)
            # migrate test cgm
            lltcc.cron_copy(conn, 'loop_logic_scott', True)
            # migrate data at test time
            migrate_all(conn, 'autoapp_scott', 'loop_logic_scott', data_in['time'])
            curs = dbi.cursor(conn)
            curs.execute('''select loop_summary_id, 
                                   bolus_pump_id, time(bolus_timestamp), bolus_type, bolus_value, 
                                   carb_id, carb_timestamp, carb_value, 
                                   anchor
                            from loop_logic_scott.loop_summary''')
            print('after', data_in)
            print_results(curs.fetchall())

def test_4():
    '''This test is about removing cancel_temp_basal that immediately precedes a temp_basal command'''
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
            curs.execute(f"insert into autoapp_scott.bolus values(%s, %s, %s, %s, %s, %s, %s)",
                         desc['vals'])
        elif desc['table'] == 'bolus_command':
            # 1 placeholder, though maybe we should allow entering the whole row, as with the others
            curs.execute(f"insert into autoapp_scott.commands(user_id, completed, type, created_timestamp) values(%s, %s, %s, %s)",
                         desc['com_vals'])
            curs.execute('select last_insert_id()')
            comm_id = curs.fetchone()[0]
            curs.execute('insert into autoapp_scott.commands_single_bolus_data values(%s, %s, 99, %s)',
                         [comm_id, desc['amt'], desc['amt']])
            curs.execute('update autoapp_scott.dana_history_timestamp set date = %s WHERE user_id = %s',
                         [desc['time'], HUGH_USER_ID])
        elif desc['table'] == 'carbs':
            curs.execute(f"insert into autoapp_scott.carbohydrate(user_id,date,value) values(%s, %s, %s)",
                         desc['vals'])
        elif desc['table'] == 'commands':
            curs.execute(f"insert into autoapp_scott.commands(user_id,created_timestamp,type) values(%s, %s, %s)",
                         desc['vals'])
        conn.commit()
        
    USER = 7
    CAN_TEMP = 'cancel_temporary_basal'
    TEMP_BASAL = 'temporary_basal'
    init_cgm(conn, start)
    for idx, scenario in enumerate([
            [
                {'table': 'commands', 'time': dt(1), 'vals': [USER, dt(1), CAN_TEMP]},
                {'table': 'commands', 'time': dt(1), 'vals': [USER, dt(1), TEMP_BASAL]},
                {'table': 'commands', 'time': dt(3), 'vals': [USER, dt(3), CAN_TEMP]},
                {'table': 'commands', 'time': dt(3), 'vals': [USER, dt(3), TEMP_BASAL]},
                {'table': 'commands', 'time': dt(7), 'vals': [USER, dt(7), CAN_TEMP]},
                {'table': 'commands', 'time': dt(7), 'vals': [USER, dt(7), TEMP_BASAL]},
                {'table': 'commands', 'time': dt(9), 'vals': [USER, dt(9), CAN_TEMP]},
             ],
    ]):
        print(f'==== scenario {idx} ===========')
        # all at once, unlike test_3
        for data_in in scenario:
            print('data in', data_in)
            insert(conn, data_in)
        # migrate test cgm
        lltcc.cron_copy(conn, 'loop_logic_scott', True)
        # migrate data; another difference from test_3
        migrate_all(conn, 'autoapp_scott', 'loop_logic_scott', start)
        curs = dbi.cursor(conn)
        curs.execute('''select loop_summary_id, 
                               command_id, created_timestamp, type
                       from loop_logic_scott.loop_summary''')
        print('after', data_in)
        print_results(curs.fetchall())

def test_5():
    '''Testing the various anchor types'''
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
            # 6 placeholders. server_time can't be null.
            curs.execute(f"insert into autoapp_scott.bolus values(NULL, %s, %s, %s, %s, %s, %s)",
                         desc['vals'])
        elif desc['table'] == 'bolus_command':
            # 1 placeholder, though maybe we should allow entering the whole row, as with the others
            curs.execute(f"insert into autoapp_scott.commands(user_id, completed, type, created_timestamp) values(%s, %s, %s, %s)",
                         desc['com_vals'])
            curs.execute('select last_insert_id()')
            comm_id = curs.fetchone()[0]
            curs.execute('insert into autoapp_scott.commands_single_bolus_data values(%s, %s, 99, %s)',
                         [comm_id, desc['amt'], desc['amt']])
            curs.execute('update autoapp_scott.dana_history_timestamp set date = %s WHERE user_id = %s',
                         [desc['time'], HUGH_USER_ID])
        elif desc['table'] == 'carbs':
            curs.execute(f"insert into autoapp_scott.carbohydrate(user_id,date,value) values(%s, %s, %s)",
                         desc['vals'])
        elif desc['table'] == 'commands':
            curs.execute(f"insert into autoapp_scott.commands(user_id,created_timestamp,type) values(%s, %s, %s)",
                         desc['vals'])
        conn.commit()
        
    USER = 7
    init_cgm(conn, start)
    for idx, scenario in enumerate([
            [
                {'table': 'bolus', 'time': dt(1), 'vals': [USER, dt(1), 'S', 3, 30, dt(1)]},
                {'table': 'bolus', 'time': dt(2), 'vals': [USER, dt(2), 'S', 4, 40, dt(2)]}, # largest, hence anchor
                {'table': 'bolus', 'time': dt(3), 'vals': [USER, dt(3), 'S', 1, 20, dt(3)]},
                {'table': 'bolus', 'time': dt(4), 'vals': [USER, dt(4), 'S', 1, 30, dt(4)]}, # top-up
                {'table': 'carbs', 'time': dt(5), 'vals': [USER, dt(20), 100]}, # lotsa carbs, so previous should be carb anchor
                {'table': 'bolus', 'time': dt(5), 'vals': [USER, dt(20), 'S', 5, 50, dt(20)]}, # carb anchor
             ],
    ]):
        print(f'==== scenario {idx} ===========')
        # all at once, unlike test_3
        for data_in in scenario:
            print('data in', data_in)
            insert(conn, data_in)
        # migrate test cgm
        lltcc.cron_copy(conn, 'loop_logic_scott', True)
        # migrate data; another difference from test_3
        migrate_all(conn, 'autoapp_scott', 'loop_logic_scott', start)
        curs = dbi.cursor(conn)
        curs.execute('''select loop_summary_id, 
                               bolus_pump_id, time(bolus_timestamp), bolus_type, bolus_value, anchor
                               carb_id, time(carb_timestamp), carb_value
                        from loop_logic_scott.loop_summary''')
        print('after', data_in)
        print_results(curs.fetchall())

def create_testing_infrastructure(start):
    test = {} # dictionary of functions for our testing infrastructure
    start_time = date_ui.to_datetime(start)
    curr_time = start_time
    def at(mins):
        nonlocal curr_time, start_time
        curr_time = start_time + timedelta(minutes=mins)
        return date_ui.str(curr_time)

    def later(mins):
        nonlocal curr_time, start_time
        curr_time += timedelta(minutes=mins)
        return date_ui.str(curr_time)

    def now():
        nonlocal curr_time
        return date_ui.str(curr_time)

    def insert(conn, desc):
        '''desc describes an insertion: tuple of time, table, cols, and
values. Time is either (at n) or (dt n), where (at n) means n minutes
after start time, and (dt n) means n minutes later. If desc is a list,
then its a set of insertions, all of which are inserted before the
next run. cols is a tuple of column names or * in which case it's
omitted and values has to be the whole row. The values tuple can have
a 'now' string, which then is replaced by the time for the insertion.

bolus_command has an extra value, which is the amount which goes in
single_bolus_data.

        '''
        if desc[0] == 'multi':
            # insert multiple things at once. They don't all have to
            # be at the same timestamp
            desc.pop(0)
            for d in desc:
                print('multi d', d)
                insert(conn,d)
            return
        print('desc', desc)
        (time, table, cols, vals, *_) = desc
        now = None
        if time[0] == 'at':
            now = at(time[1])
        if time[1] == 'dt':
            now = later(time[1])
        print('now', now)
        def cnvt(x):
            if x == 'now':
                return now
            return x
        def NN(s):
            return s.replace("None", "NULL")
        vals_now = tuple([ cnvt(v) for v in vals ])
        print('vals_now', vals_now, 'len', len(vals_now))
        curs = dbi.cursor(conn)
        if table == 'bolus':
            # 7 cols: bolus_id (auto), user_id, date, type, value, duration, server_date=current_timestamp
            # the last can't be NULL
            if cols == '*':
                curs.execute(NN(f"insert into autoapp_scott.bolus values {vals_now}"))
            else:
                curs.execute(NN(f"insert into autoapp_scott.bolus{cols} values {vals_now}"))
        elif table == 'bolus_command':
            # 11 columns
            if cols == '*':
                curs.execute(NN(f"insert into autoapp_scott.commands values {vals_now}"))
            else:
                raise Error('not yet implemented')
                curs.execute(NN(f"insert into autoapp_scott.commands{cols} values {vals_now}"))
            curs.execute('select last_insert_id()')
            comm_id = curs.fetchone()[0]
            amt = desc[4]
            curs.execute(f'insert into autoapp_scott.commands_single_bolus_data values({comm_id}, {amt}, 0, {amt})')
            curs.execute(f'''update autoapp_scott.dana_history_timestamp set date = '{now}' WHERE user_id = {HUGH_USER_ID}''')
        elif table =='carbs':
            # 5 columns. First is carb_id (auto), user_id, date, value, and last is current_timestamp
            if cols == '*':
                curs.execute(NN(f"insert into autoapp_scott.carbohydrate values {vals_now}"))
            else:
                curs.execute(NN(f"insert into autoapp_scott.carbohydrate{cols} values {vals_now}"))
        elif table == 'commands':
            # 11 columns
            if cols == '*':
                curs.execute(NN(f"insert into autoapp_scott.commands values {vals_now}"))
            else:
                curs.execute(NN(f"insert into autoapp_scott.commands{cols} values {vals_now}"))
        else:
            raise Error('no such table')
        conn.commit()
    return (insert, now, at, later)


def test_sept_23():
    '''Janice entered the following data on 9/22 but my code got an error. This re-tests that scenario.

    Bolus of 4 Units created at 9:04 (and carried out at 9:06) should be associated with the carb entry at 9:04 and called a carb bolus/Anchor #3
    Bolus of 2 units created at 9:12 (and carried out at 9:13) should be a correction bolus and tagged as Anchor #1 (the largest correction bolus in the last bolus interval)
    Bolus of 5 units created at 9:32 (and carried out at 9:40) should be a correction bolus.  Since it is larger than the prior Anchor #1, it becomes Anchor #1.
    The loop summary shows a temp basal entry (loop summary ID 499).  Not sure how this got here.  There is an entry in the temp basal state table that looks like it was entered when I started up the loop this morning.  However, It says the temp basal is not running (temp basal in progress field is 0) so I don’t think we need this in the loop summary table.  The only time we need to see if a temp basal is not running is if the previous entry for a temp basal had a “running” entry of “1”.  In that case, we want to know that the temp basal is no longer running.  However, the last temp basal entry in loop summary had a “running” of 0.
    At 10:02, I did give a temp basal command which was carried out at 10:02.
    At 10:15, I gave another bolus of 1unit.  This should be a correction bolus and given an Anchor #2 since it is smaller than Anchor #1 and within the last bolus interval.

 '''
    start = date_ui.to_datetime('2023-05-01 12:00:00')
    (insert, now, at, later) = create_testing_infrastructure(start)
    conn = dbi.connect()
    test_clear_scott_db_and_start(conn)
    dest = 'loop_logic_scott'
    source = 'autoapp_scott'
    set_data_migration(conn, source, dest, start)
    USER = 7
    init_cgm(conn, start)
    # just one scenario
    for desc in [ [ 'multi',
                    ( ('at', 4), 'bolus', '*', (None, USER, 'now', 'S', 4, 0, 'now')), # 4 units
                    ( ('at', 4), 'carbs', '*', (None, USER, 'now', 20, 'now')) # 20 carbs
                   ],
                  ( ('at', 12), 'bolus', '*', (None, USER, 'now', 'S', 2, 0, 'now')),
                  ( ('at', 32), 'bolus', '*', (None, USER, 'now', 'S', 5, 0, 'now')),
                 ]: 
        print('main function, desc', desc)
        insert(conn, desc)
        lltcc.cron_copy(conn, 'loop_logic_scott', True)
        migrate_all(conn, 'autoapp_scott', 'loop_logic_scott', now())
        print('after', desc)
        print(table_output(conn, 
                           '''select loop_summary_id as ls_id,
                               bolus_pump_id as bp_id, 
                               time(bolus_timestamp) as bolus_time, bolus_type, bolus_value, anchor,
                               carb_id, time(carb_timestamp) as carb_time, carb_value
                           from loop_logic_scott.loop_summary'''))

def test_oct13():
    '''We're getting duplicates of boluses, once not as a command and once as a command. 

 '''
    start = date_ui.to_datetime('2023-05-01 12:00:00')
    (insert, now, at, later) = create_testing_infrastructure(start)
    conn = dbi.connect()
    test_clear_scott_db_and_start(conn)
    dest = 'loop_logic_scott'
    source = 'autoapp_scott'
    set_data_migration(conn, source, dest, start)
    USER = 7
    init_cgm(conn, start)
    # just one scenario
    for desc in [ [ 'multi',
                    ( ('at', 4), 'bolus_command', '*', (None, USER, 'now', 'now', 'bolus', 1, 0, 'done', 0, 0, 0), 5), # 5 units
                    ( ('at', 4), 'bolus', '*', (None, USER, 'now', 'S', 5, 0, 'now')) # 5 units
                   ],
                 ]: 
        print('main function, desc', desc)
        insert(conn, desc)
        lltcc.cron_copy(conn, 'loop_logic_scott', True)
        migrate_all(conn, 'autoapp_scott', 'loop_logic_scott', now())
        print('after', desc)
        print(table_output(conn, 
                           '''select loop_summary_id as ls_id,
                               bolus_pump_id as bp_id, 
                               time(bolus_timestamp) as bolus_time, bolus_type, bolus_value, anchor,
                               carb_id, time(carb_timestamp) as carb_time, carb_value
                           from loop_logic_scott.loop_summary'''))

def test_caseA():
    '''just carbs, no boluses, no no anchor type to worry about.'''
    start = date_ui.to_datetime('2023-05-01 12:00:00')
    (insert, now, at, later) = create_testing_infrastructure(start)
    conn = dbi.connect()
    test_clear_scott_db_and_start(conn)
    dest = 'loop_logic_scott'
    source = 'autoapp_scott'
    set_data_migration(conn, source, dest, start)
    USER = 7
    init_cgm(conn, start)
    for desc in [ ( ('at', 4), 'carbs', '*', (None, USER, 'now', 20, 'now'))
                  ,( ('at', 34), 'carbs', '*', (None, USER, 'now', 10, 'now'))
                  ,( ('at', 44), 'carbs', '*', (None, USER, 'now', 30, 'now'))
                 ]:
        print('main function, desc', desc)
        insert(conn, desc)
        lltcc.cron_copy(conn, 'loop_logic_scott', True)
        migrate_all(conn, 'autoapp_scott', 'loop_logic_scott', now())
        print('after', desc)
        print(table_output(conn, 
                           '''select loop_summary_id as ls_id,
                               bolus_pump_id as bp_id, 
                               time(bolus_timestamp) as bolus_time, bolus_type, bolus_value, anchor,
                               carb_id, time(carb_timestamp) as carb_time, carb_value
                           from loop_logic_scott.loop_summary'''))
    
def test_caseB():
    '''unmatched bolus (case C) followed by matching carbs (case B).'''
    start = date_ui.to_datetime('2023-05-01 12:00:00')
    (insert, now, at, later) = create_testing_infrastructure(start)
    conn = dbi.connect()
    test_clear_scott_db_and_start(conn)
    dest = 'loop_logic_scott'
    source = 'autoapp_scott'
    set_data_migration(conn, source, dest, start)
    USER = 7
    init_cgm(conn, start)
    for desc in [ ( ('at', 4), 'bolus', '*', (None, USER, 'now', 'S', 5, 0, 'now')) # 5 unit bolus; anchor = 3
                  ,( ('at', 5), 'carbs', '*', (None, USER, 'now', 20, 'now')) # 20 carbs
                  ,( ('at', 23), 'bolus', '*', (None, USER, 'now', 'S', 2, 0, 'now')) # 2 unit bolus. Is this correction or carbs?
                 #  ,( ('at', 200), 'carbs', '*', (None, USER, 'now', 30, 'now')) # 30 carbs
                 #  ,( ('at', 205), 'bolus', '*', (None, USER, 'now', 'S', 5, 0, 'now')) # 5 unit bolus; anchor = 3
                 #  ,( ('at', 215), 'bolus', '*', (None, USER, 'now', 'S', 6, 0, 'now')) # 6 unit bolus; anchor = 3
                 ]:
        print('main function, desc', desc)
        insert(conn, desc)
        lltcc.cron_copy(conn, 'loop_logic_scott', True)
        migrate_all(conn, 'autoapp_scott', 'loop_logic_scott', now())
        print('after', desc)
        print(table_output(conn, 
                           '''select loop_summary_id as ls_id,
                               bolus_pump_id as bp_id, 
                               time(bolus_timestamp) as bolus_time, bolus_type, bolus_value, anchor,
                               carb_id, time(carb_timestamp) as carb_time, carb_value
                           from loop_logic_scott.loop_summary'''))
    

def test_caseC():
    '''correction boluses. If increasing, we get a new anchor. If decreasing, we get a top-up. '''
    start = date_ui.to_datetime('2023-05-01 12:00:00')
    (insert, now, at, later) = create_testing_infrastructure(start)
    conn = dbi.connect()
    test_clear_scott_db_and_start(conn)
    dest = 'loop_logic_scott'
    source = 'autoapp_scott'
    set_data_migration(conn, source, dest, start)
    USER = 7
    init_cgm(conn, start)
    for desc in [ ( ('at', 5), 'bolus', '*', (None, USER, 'now', 'S', 5, 0, 'now')) # 5 unit bolus; anchor = 1
                  ,( ('at', 23), 'bolus', '*', (None, USER, 'now', 'S', 2, 0, 'now')) # 2 unit bolus; anchor = 2 (top-up)
                  ,( ('at', 25), 'bolus', '*', (None, USER, 'now', 'S', 1, 0, 'now')) # 2 unit bolus; anchor = 2 (top-up)
                  ,( ('at', 305), 'bolus', '*', (None, USER, 'now', 'S', 5, 0, 'now')) # 5 unit bolus; anchor = 1
                  ,( ('at', 315), 'bolus', '*', (None, USER, 'now', 'S', 6, 0, 'now')) # 6 unit bolus; anchor = 1
                 ]:
        print('main function, desc', desc)
        insert(conn, desc)
        lltcc.cron_copy(conn, 'loop_logic_scott', True)
        migrate_all(conn, 'autoapp_scott', 'loop_logic_scott', now())
        print('after', desc)
        print(table_output(conn, 
                           '''select loop_summary_id as ls_id,
                               bolus_pump_id as bp_id, 
                               time(bolus_timestamp) as bolus_time, bolus_type, bolus_value, anchor,
                               carb_id, time(carb_timestamp) as carb_time, carb_value
                           from loop_logic_scott.loop_summary'''))
    
def test_caseD():
    '''unmatched carbs (case A) followed by matching bolus (case D).'''
    start = date_ui.to_datetime('2023-05-01 12:00:00')
    (insert, now, at, later) = create_testing_infrastructure(start)
    conn = dbi.connect()
    test_clear_scott_db_and_start(conn)
    dest = 'loop_logic_scott'
    source = 'autoapp_scott'
    set_data_migration(conn, source, dest, start)
    USER = 7
    init_cgm(conn, start)
    for desc in [ ( ('at', 4), 'carbs', '*', (None, USER, 'now', 30, 'now')) # 30 carbs (dinner?)
                  ,( ('at', 5), 'bolus', '*', (None, USER, 'now', 'S', 5, 0, 'now')) # 5 unit bolus; anchor = 3
                  ,( ('at', 40), 'carbs', '*', (None, USER, 'now', 10, 'now')) # 10 more carbs (dessert?)
                  ,( ('at', 42), 'bolus', '*', (None, USER, 'now', 'S', 2, 0, 'now')) # 2 unit bolus; anchor = NULL
                 ]:
        print('main function, desc', desc)
        insert(conn, desc)
        lltcc.cron_copy(conn, 'loop_logic_scott', True)
        migrate_all(conn, 'autoapp_scott', 'loop_logic_scott', now())
        print('after', desc)
        print(table_output(conn, 
                           '''select loop_summary_id as ls_id,
                               bolus_pump_id as bp_id, 
                               time(bolus_timestamp) as bolus_time, bolus_type, bolus_value, anchor,
                               carb_id, time(carb_timestamp) as carb_time, carb_value
                           from loop_logic_scott.loop_summary'''))
    



def to_dictionary(dic_list):
    result = {}
    for d in dic_list:
        for key,val in d.items():
            if key in result:
                result[key].append(val)
            else:
                result[key] = [val]
    return result

def table_output(conn, sql):
    '''Runs SQL code and returns a string that is a nice tabular output. '''
    curs = dbi.dict_cursor(conn)
    curs.execute(sql)
    vals = curs.fetchall()
    cols = to_dictionary(vals)
    widths = {}
    for key,val in cols.items():
        widths[key] = max(len(key), max(map(lambda x: len(str(x)), val)))
    table = ''
    for key in cols.keys():
        table += '\t'+key.rjust(widths[key])
    table += '\n'
    for row in vals:
        for key,val in row.items():
            table += '\t'+str(val).rjust(widths[key])
        table += '\n'
    return table

def col_widths(row_list):
    if len(row_list) == 0:
        raise ValueError('empty list')
    widths = [0] * len(row_list[0])
    for row in row_list:
        for idx,col in enumerate(row):
            widths[idx] = max(widths[idx], len(str(col)))
    return widths

def print_results(row_list):
    widths = col_widths(row_list)
    for row in row_list:
        out = ''
        for idx,col in enumerate(row):
            out += '\t'+str(col).rjust(widths[idx])
        print(out)
        # print('\t'+'|'.join([str(x) for x in row]))


def logfile_start(source):
    '''logfile is in file {source}{date} like 'autoapp_test15'. '''
    # The default is to run as a cron job
    # when run as a script, log to a logfile 
    today = datetime.today()
    logfile = os.path.join(LOG_DIR, source+str(today.day))
    now = datetime.now()
    if now.hour == 0 and now.minute==0:
        try:
            os.unlink(logfile)
        except FileNotFoundError:
            pass
    # The logging software doesn't allow more than one basicConfig, so
    # logging to different files is difficult. 
    logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s',
                        datefmt='%H:%M',
                        filename=logfile,
                        level=logging.DEBUG)
    if now.hour == 0 and now.minute==0:
        logging.info('================ first run of the day!!'+str(now))
    logging.info('SCOTT running at {} logging {}'.format(datetime.now(), logfile))

def logfile_start_new(source):
    # The default is to run as a cron job
    # when run as a script, log to a logfile 
    global logstream, loghandler
    today = datetime.today()
    logfile = os.path.join(LOG_DIR, source+str(today.day))
    now = datetime.now()
    if now.hour == 0 and now.minute==0:
        try:
            os.unlink(logfile)
        except FileNotFoundError:
            pass
    # The logging software doesn't allow more than one basicConfig, so
    # logging to different files is difficult. 
    logstream = open(logfile, 'a')
    h = logging.StreamHandler(logstream)
    logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s',
                        datefmt='%H:%M',
                        level=logging.DEBUG)
    logger = logging.getLogger()
    if loghandler is not None:
        logger.removeHandler(loghandler)
    loghandler = h
    logger.addHandler(loghandler)
    if now.hour == 0 and now.minute==0:
        logging.info('================ first run of the day!!'+str(now))
    logging.info('running at {}'.format(datetime.now(), logfile))

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
    migrate_all(conn, 'autoapp', 'loop_logic')
    migrate_all(conn, 'autoapp_test', 'loop_logic_test')

'''
SELECT loop_summary_id, 
       time(bolus_timestamp) as bolus_time, bolus_pump_id, bolus_type, bolus_value, 
       carb_id, time(carb_timestamp) as carb_time, carb_value,
       created_timestamp, state, type, completed, linked_cgm_value, anchor FROM `loop_summary` ORDER BY `loop_summary_id` DESC ;
'''
