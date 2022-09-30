'''Migrates Hugh's records from the autoapp database to tables in the loop_logic database.

See https://docs.google.com/document/d/1n_lxiAqkgNiQgVSVidOo-5bntfIo5aQF/edit

realtime_cgm is migrated from janice.realtime_cgm2; that's separate
from all others, so it's pretty easy.

Next, we migrate all bolus and carb data for the last max_bolus_interval (a
field in the glucose range table).  Use 6 hours if missing.

Testing: start python, and run the functions in 




'''

import os                       # for path.join
import sys
import math                     # for floor
import collections              # for deque
import cs304dbi as dbi
from datetime import datetime, timedelta
import date_ui
import logging

# Configuration Constants

# probably should have different logs for production vs development
LOG_DIR = '/home/hugh9/autoapp_to_loop_logic_logs/'

HUGH_USER = 'Hugh'
HUGH_USER_ID = 7


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



def get_cgm_update_times(conn):
    '''Long discussion about the data to migrate. See
https://docs.google.com/document/d/1ZCtErlxRQmPUz_vbfLXdg7ap2hIz5g9Lubtog8ZqFys/edit#heading=h.umdjcuqs1gq4

This function also looks in the janice.realtime_cgm2 table and finds
the most recent value where mgdl is not None (Y). We should probably
store that useful value somewhere. It also returns the prior value of
that, we stored as loop_logic.migration_status.prev_cgm_update
(PY). Returns both (Y,PY) if Y > Py, otherwise None, None.

    '''
    (rtime, dexcom_time) = get_latest_stored_data(conn)
    last_cgm = min(rtime, dexcom_time)
    curs = dbi.cursor(conn)
    curs.execute('''select prev_cgm_update from loop_logic.migration_status where user_id = %s''',
                 [HUGH_USER_ID])
    prev_cgm = curs.fetchone()[0]
    logging.debug(f'last update from dexcom was at {last_cgm}; the previous value was {prev_cgm}')
    if prev_cgm < last_cgm:
        # new data, so return the time to migrate since
        return prev_cgm, last_cgm # increasing order
    else:
        return None, None
    

def set_cgm_migration_time(conn, prev_update, last_update):
    '''Long discussion about the data to migrate. See
https://docs.google.com/document/d/1ZCtErlxRQmPUz_vbfLXdg7ap2hIz5g9Lubtog8ZqFys/edit#heading=h.umdjcuqs1gq4

This function sets the value of prev_update_time in the
loop_logic.migration_status table to the time of the lastest real data in janice.realtime_cgm2.

It uses the passed-in values, to avoid issues of simultaneous updates. Ignores prev_update, uses last_update

    '''
    logging.debug(f'setting prev {prev_update} and last {last_update} cgm update times')
    curs = dbi.cursor(conn)
    curs.execute('''UPDATE loop_logic.migration_status 
                    SET prev_cgm_update = %s, prev_cgm_migration = current_timestamp() 
                    WHERE user_id = %s''',
                 # notice this says last_ not prev_; we ignore prev here
                 [last_update, HUGH_USER_ID])
    conn.commit()
    return 'done'

def get_autoapp_update_times(conn):
    '''Long discussion about the data to migrate. See
https://docs.google.com/document/d/1ZCtErlxRQmPUz_vbfLXdg7ap2hIz5g9Lubtog8ZqFys/edit#heading=h.umdjcuqs1gq4

This function looks up the values of
autoapp.dana_history_timestamp.date (X) and
loop_logic.migration_status.prev_autoapp_update (PX) and returns (X, PX)
iff X > PX otherwise None,None.

It returns all values so that new values can be stored into
migration_status when we are done migrating. See set_migration_time.

    '''
    curs = dbi.cursor(conn)
    curs.execute('''select date from autoapp.dana_history_timestamp where user_id = %s''',
                 [HUGH_USER_ID])
    last_autoapp_update = curs.fetchone()[0]
    curs.execute('''select prev_autoapp_update from loop_logic.migration_status where user_id = %s''',
                 [HUGH_USER_ID])
    prev_autoapp = curs.fetchone()[0]
    if prev_autoapp < last_autoapp_update:
        # new data since last migration, so return the time to migrate since
        return prev_autoapp, last_autoapp_update # increasing order
    else:
        return None, None

def set_autoapp_migration_time(conn, prev_update, last_update):
    '''Long discussion about the data to migrate. See
https://docs.google.com/document/d/1ZCtErlxRQmPUz_vbfLXdg7ap2hIz5g9Lubtog8ZqFys/edit#heading=h.umdjcuqs1gq4

This function sets the value of prev_autoappupdate in the
loop_logic.migration_status table to the time of the lastest real data
in autoapp.dana_history_timestamp

It uses the passed-in values, to avoid issues of simultaneous updates.

    '''
    logging.debug(f'setting prev {prev_update} and last {last_update} autoapp update times')
    curs = dbi.cursor(conn)
    curs.execute('''UPDATE loop_logic.migration_status 
                    SET prev_autoapp_update = %s, prev_autoapp_migration = current_timestamp() 
                    WHERE user_id = %s''',
                 # notice this says last_ not prev_; we ignore prev here
                 [last_update, HUGH_USER_ID])
    conn.commit()
    return 'done'


# ================================================================

def migrate_cgm(conn, start_time, commit=True):
    '''start_time is a string or a python datetime'''
    if conn is None:
        conn = dbi.connect()
    curs = dbi.cursor(conn)
    logging.debug(f'migrating realtime_cgm since {start_time}')
    nrows = curs.execute('''select user_id,trend,dexcom_time,mgdl 
                            from janice.realtime_cgm2
                            where dexcom_time > %s''',
                 [start_time])
    logging.debug(f'got {nrows} from realtime_cgm2')
    ins = dbi.cursor(conn)
    for row in curs.fetchall():
        # we can't use on duplicate key, because the key is an auto_increment value that we don't have.
        # So we have to look for matches on timestamp values. 
        (user_id, _, dexcom_timestamp_utc, _) = row
        nr = ins.execute('''select cgm_id from loop_logic.realtime_cgm 
                            where user_id = %s and dexcom_timestamp_utc = %s''',
                         [user_id, dexcom_timestamp_utc])
        logging.debug(f'found {nr} matches (already migrated rows)')
        if nr == 0:
            ins.execute('''insert into loop_logic.realtime_cgm(cgm_id,user_id,trend,dexcom_timestamp_utc,cgm_value)
                           values(null,%s,%s,%s,%s)''',
                        row)
    if commit:
        conn.commit()

def migrate_cgm_test(conn, start_time):
    if conn is None:
        conn = dbi.connect()
    curs = dbi.cursor(conn)
    curs.execute('select count(*) from loop_logic.realtime_cgm;')
    count_before = curs.fetchone()[0]
    print(f'before, there are {count_before}')
    # don't commit when testing. It'll be true in this connection, but not permanent
    migrate_cgm(conn, start_time, False)
    curs.execute('select count(*) from loop_logic.realtime_cgm;')
    count_after = curs.fetchone()[0]
    print(f'after, there are {count_after}')
        
def migrate_cgm_updates(conn):
    '''migrate all the new cgm values, since the last time we migrated.'''
    prev_cgm_update, last_cgm_update = get_cgm_update_times(conn)
    if prev_cgm_update is None:
        # punt, because there's no new data
        return
    migrate_cgm(conn, prev_cgm_update)
    set_cgm_migration_time(conn, prev_cgm_update, last_cgm_update)

# ================================================================
# Bolus functions

def get_max_bolus_interval_mins(conn, user_id=HUGH_USER_ID):
    '''Look up the max_bolus_interval in the glucose_range table for the given user_id'''
    if conn is None:
        conn = dbi.connect()
    curs = dbi.cursor(conn)
    DEFAULT = 6*60
    return DEFAULT
    nrows = curs.execute('''select max_bolus_interval_mins 
                            from loop_logic.glucose_range inner join loop_logic.user using(glucose_range_id)
                            where user_id = %s''',
                         [user_id])
    if nrows == 0:
        return DEFAULT
    row = curs.fetchone()
    if row is None:
        return DEFAULT
    return row[0]
        
'''
  `bolus_id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `date` datetime NOT NULL,
  `type` varchar(2) NOT NULL,
  `value` double NOT NULL,
  `duration` double NOT NULL,
  `server_date` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
'''

def matching_cgm(conn, timestamp):
    '''Returns two values, the cgm_id and cgm_value value from the
realtime_cgm table where its timestamp is closest in time to the given
timestamp, which is probably the timestamp of a bolus.

    '''
    curs = dbi.cursor(conn)
    query = '''SELECT cgm_id, cgm_value from loop_logic.realtime_cgm
               WHERE user_id = %s AND 
               abs(time_to_sec(timediff(dexcom_timestamp_utc, %s))) = 
                  (select min(abs(time_to_sec(timediff(dexcom_timestamp_utc, %s)))) 
                   from loop_logic.realtime_cgm)'''
    nr = curs.execute(query, [HUGH_USER_ID, timestamp, timestamp])
    if nr > 1:
        # ick. could there be two exactly the same distance? 
        for row in curs.fetchall():
            print(row)
        logging.error(f'found {nr} matching CGM values for timestamp {timestamp} ')
    row = curs.fetchone()
    if row is None:
        logging.error(f'no matching CGM for timestamp {timestamp}')
        return None
    else:
        (cgm_id, cgm_value) = row
        return row

def get_boluses(conn, start_time):
    '''Return a list of recent boluses (anything after start_time) as a
list of tuples. We only need to look at the bolus table, since
we just want bolus_pump_id, date, value and type. If the bolus ends up
being associated with a command, we'll update the entry later.

    '''
    curs = dbi.cursor(conn)
    # ignore type and duration?
    # note: bolus_id is called bolus_pump_id in loop_logic
    curs.execute('''select user_id, bolus_id, date, value 
                    from autoapp.bolus
                    where date >= %s''',
                 [start_time])
    return curs.fetchall()
    
def migrate_boluses(conn, start_time, commit=True):
    '''start_time is a string or a python datetime. '''
    if conn is None:
        conn = dbi.connect()
    curs = dbi.cursor(conn)
    # Note that these will probably be *new* rows, but to make this
    # idempotent, we'll look for a match on the date.
    boluses = get_boluses(conn, start_time)
    for row in boluses:
        # note: bolus_id is called bolus_pump_id in loop_logic
        (user_id, bolus_pump_id, date, value) = row
        # see if all values match
        curs.execute('''select loop_summary_id, user_id, bolus_pump_id, bolus_timestamp, bolus_value
                        from loop_logic.loop_summary
                        where user_id = %s and bolus_pump_id = %s and bolus_timestamp = %s and bolus_value = %s''',
                     row)
        match = curs.fetchone()
        if match is None:
            # the normal case
            (cgm_id, cgm_value) = matching_cgm(conn, date)
            curs.execute('''insert into loop_logic.loop_summary
                                (user_id, bolus_pump_id, bolus_timestamp, bolus_value,
                                linked_cgm_id
                                )
                            values(%s, %s, %s, %s, %s)''',
                         [user_id, bolus_pump_id, date, value, cgm_id])
        else:
            # already exists, so update? Ignore? We'll complain if they differ
            logging.info('bolus match: this bolus is already migrated: %s'.format(row))
            
    if commit:
        conn.commit()
    


def migrate_all(conn, alt_start_time=None):
    '''This is the function that should, eventually, be called from a cron job every 5 minutes.
If alt_start_time is supplied, ignore the value from the get_migration_time() table.'''
    if conn is None:
        conn = dbi.connect()
    logging.info('starting')
    logging.info('1. realtime cgm')
    migrate_cgm_updates(conn)
    prev_update, last_autoapp_update = get_autoapp_update_times(conn)
    if prev_update is None:
        # if prev_update is None, that means there's no new data in autoapp
        # since we last migrated, so save ourselves some work by giving up now
        logging.info('no new data, so giving up')
        return
    start_time = alt_start_time or prev_update
    logging.info(f'migrating data since {start_time}')
    logging.info('2. bolus')
    migrate_boluses(conn, start_time)
    logging.info('done. storing update time')
    set_autoapp_migration_time(conn, prev_update, last_autoapp_update)
    logging.info('done')


if __name__ == '__main__': 
    conn = dbi.connect()
    # we use this when we've cleared out the database and started again
    if len(sys.argv) > 1 and sys.argv[1] == 'migrate_cgm':
        alt_start_time = sys.argv[2]
        debugging()
        migrate_cgm(conn, alt_start_time, True)
        set_cgm_migration_time(conn, alt_start_time, alt_start_time)
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

