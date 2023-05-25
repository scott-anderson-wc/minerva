'''Code to run as a cron job. Uses the tables defined in loop-logic-latest-cgm.sql namely

{dest}.realtime_cgm

migrating test data from 

{dest}.source_cgm

When the loop_logic.testing_command table as a non-empty string in the 'command' column,
we start or stop the testing.  That means:

1. clear the value of the command
2. change the status from OFF to ON if the command is 'start', if command is 'stop', change from ON to OFF
3. put the current time in the 'start' column
4. if the command is not in ('start', 'stop'), put an error message in msg column.

As as cron job, we copy cgm values from source_cgm iff either
   testing_command.status == 'ON'
   testing_command.command in ['start', 'restart']

Scott Anderson
Sep 28 2022

May 12, added a "dest" keyword argument to each function, so that we
can decide to work with loop_logic and/or loop_logic_test.

May 18, revised so that the data flows to realtime_cgm instead of to
latest_cgm. Also, created function in_test_mode() which can be shared
with autoapp_to_loop_logic.

'''

import sys
import cs304dbi as dbi
from datetime import datetime

USER_ID = 7

# these values are modifiable if we want to test this testing code
# also avoids mispelling the table name

TESTING_COMMAND = 'testing_command'
REALTIME_CGM = 'realtime_cgm'
SOURCE_CGM = 'source_cgm'

# I wonder if this should be an environment variable, to avoid having to edit this file
TESTING_THE_TESTING = False

def in_test_mode(conn, dest='loop_logic_test'):
    '''Returns boolean, whether we are in testing mode or
not. autoapp_to_loop_logic uses this to turn off migration of real CGM
data.'''
    curs = conn.cursor()
    curs.execute(f'select command, status from {dest}.{TESTING_COMMAND} where comm_id = 1')
    (command, status) = curs.fetchone()
    return status == 'ON' or command in ['start', 'restart']

def cron_start(conn, dest='loop_logic'):
    '''Records info in testing_command when a testing run begins'''
    curs = conn.cursor()
    curs.execute(f'''UPDATE {dest}.{TESTING_COMMAND} 
                    SET command = '', status = 'ON', start = current_timestamp(), msg = ''
                    WHERE comm_id = 1''')
    # this will update all rows, so we can reuse the testing data
    curs.execute(f'''UPDATE {dest}.{SOURCE_CGM}
                    SET used = 'NO'; ''')
    conn.commit()

def cron_stop(conn, dest='loop_logic'):
    '''Set status back to OFF to turn off the migration. '''
    curs = conn.cursor()
    now_raw = datetime.now()
    now = now_raw.replace(microsecond=0) # ugly to have the microsecond in a msg, so truncate
    msg = f'ended testing at {now}'
    curs.execute(f'''UPDATE {dest}.{TESTING_COMMAND} 
                    SET command = '', status = 'OFF', start = NULL, msg = %s
                    WHERE comm_id = 1''',
                 [msg])
    conn.commit()

def cron_copy(conn, dest='loop_logic', use_fake_time=False):
    '''Normal processing. Take the next value from the source_cgm table,
determined by the min rtime where used is NO.  This is coded under the
assumption that it might run until we run out of fake entries in
source_cgm and that when we run out we want to clear out the fake
entries from realtime_cgm, and reset everything, so the fake entries
will be copied repetitively forever. 5/18 They are no longer marked
fake; instead they'll be identified by timestamp.
    '''
    row = get_next_unused_test_value(conn, dest=dest)
    if row is None:
        if TESTING_THE_TESTING:
            print(f'out of test data; stopping')
        # 5/18 if row is none, out of test data, so just stop
        cron_stop(conn, dest)
        return
    if TESTING_THE_TESTING:
        print(f'copying row {row}')
    (user_id, rtime, mgdl, trend, trend_code) = row
    # mark it as used
    curs = conn.cursor()
    curs.execute(f'''UPDATE {dest}.{SOURCE_CGM} SET used = 'YES' WHERE rtime = %s''', [rtime])
    conn.commit()
    if use_fake_time:
        curs.execute(f'''INSERT INTO {dest}.{REALTIME_CGM}
                         VALUES(NULL, 7, %s, %s, %s, %s)''',
                     [rtime, mgdl, trend, trend_code])
    else:
        # Insert it into the real table, substituting current_timestamp() for rtime
        curs.execute(f'''INSERT INTO {dest}.{REALTIME_CGM}
                         VALUES(NULL, 7, current_timestamp(), %s, %s, %s)''',
                     [mgdl, trend, trend_code])
    conn.commit()
    # For debugging, let's put a message in the command table
    msg = f'copied {rtime}, {mgdl}, {trend}, {trend_code}'
    curs.execute(f'''UPDATE {dest}.{TESTING_COMMAND} 
                    SET msg = %s 
                    WHERE comm_id = 1''',
                 [msg])
    conn.commit()

def get_next_unused_test_value(conn, dest='loop_logic'):
    '''search for the next value to copy, the min rtime among unused test
values. Returns a tuple from source_cgm: 

(user_id, rtime, mgdl, trend, trend_code)
'''
    curs = conn.cursor()
    curs.execute(f'''SELECT user_id, rtime, mgdl, trend, trend_code
                    FROM {dest}.{SOURCE_CGM}
                    WHERE rtime = (SELECT min(rtime) 
                                   FROM {dest}.{SOURCE_CGM} 
                                   WHERE used = 'NO');''')
    # one row or None if there are none left
    return curs.fetchone()
    

def reset_and_start_over(conn, dest='loop_logic'):
    '''Use this to clear the copied records to start over. This code is
similar to cron_start; if we wanted to put the current timestamp into
the command table whenever we restart, we could just use that
function.'''
    curs = conn.cursor()
    # delete the fake entries from realtime_cgm: anything since start of the test
    curs.execute(f'select start from {dest}.{TESTING_COMMAND} where comm_id = 1')
    startTuple = curs.fetchone()
    curs.execute(f'DELETE FROM {dest}.{REALTIME_CGM} WHERE dexcom_time >= %s', startTuple)
    conn.commit()
    # update all the source entries, marking them unused
    curs.execute(f'''UPDATE {dest}.{SOURCE_CGM} SET used = 'NO'; ''')
    conn.commit()
    

def run_as_cron(dest='loop_logic'):
    '''The processing we do when we run as a cron job: figure out what
needs doing, and dispatch to the appropriate function. We are either
getting a START command, getting a STOP command, or doing a regular
copy of the next test value.'''
    conn = dbi.connect()
    curs = conn.cursor()
    curs.execute(f'select command, status from {dest}.{TESTING_COMMAND} where comm_id = 1')
    (command, status) = curs.fetchone()
    command = command.lower().strip()
    if TESTING_THE_TESTING:
        print(f'before {command}')
        curs.execute(f'select * from {dest}.{REALTIME_CGM}')
        for row in curs.fetchall():
            print(row)
    if command == 'start':
        cron_start(conn, dest=dest)
        cron_copy(conn, dest=dest)
    elif command == 'stop':
        cron_stop(conn, dest=dest)
    elif command == 'restart':
        # a lot like start
        reset_and_start_over(conn, dest=dest)
        cron_copy(conn, dest=dest)
    elif command != '':
        msg = f'Did not understand this command: {command}. Expected "start" or "stop" without quotation marks'
        curs.execute(f'update {dest}.{TESTING_COMMAND} set msg = % where comm_id = 1',
                     [msg])
    elif status == 'ON':
        # normal case when testing is ON
        cron_copy(conn, dest=dest)
    if TESTING_THE_TESTING:
        print(f'after {command}')
        curs.execute(f'select * from {dest}.{REALTIME_CGM}')
        for row in curs.fetchall():
            print(row)


# ==================================================================
'''
to test this procedure: 

(0) modify the TESTING_THE_TESTING constant to be True 
(1) run the code in loop_logic_testing_cgm_cron.sql in mysql
(2) start up phpmyadmin, just like Janice would, and navigate to database lltt and set the value to start the test 
(3) run the script from the command line, 5-6 times

'''

if __name__ == '__main__': 
    if TESTING_THE_TESTING:
        print('testing the testing code')
        run_as_cron(dest='lltt')
    else:
        # normal operation, but every 5 minutes, so test the time
        now = datetime.now()
        if (now.minute % 5) == 0:
            run_as_cron(dest='loop_logic')
            run_as_cron(dest='loop_logic_test')
        else:
            pass
