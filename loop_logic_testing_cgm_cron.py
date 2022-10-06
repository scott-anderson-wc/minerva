'''Code to run as a cron job. Uses the tables defined in loop-logic-latest-cgm.sql namely

latest_cgm

migrating test data from 

source_cgm


When the loop_logic.testing_command table as a non-empty string in the 'command' column,
we start or stop the testing.  That means:

1. clear the value of the command
2. change the status from OFF to ON if the command is 'start', if command is 'stop', change from ON to OFF
3. put the current time in the 'start' column
4. if the command is not in ('start', 'stop'), put an error message in msg column.

As as cron job, we copy cgm values from source_cgm iff either
   testing_command.command == 'start' OR
   testing_command.status == 'ON'

Scott Anderson
Sep 28 2022

'''

import sys
import cs304dbi as dbi
from datetime import datetime

USER_ID = 7

def cron_start(conn):
    '''Records info in testing_command when a testing run begins'''
    curs = conn.cursor()
    curs.execute('''UPDATE loop_logic.testing_command 
                    SET command = '', status = 'ON', start = current_timestamp(), msg = ''
                    WHERE comm_id = 1''')
    # this will update all rows, so we can reuse the testing data
    curs.execute('''UPDATE loop_logic.source_cgm
                    SET used = 'NO'; ''')
    conn.commit()

def cron_stop(conn):
    '''Set status back to OFF to turn off the migration.'''
    curs = conn.cursor()
    now = datetime.now()
    msg = f'ended testing at {now}'
    curs.execute('''UPDATE loop_logic.testing_command 
                    SET command = '', status = 'OFF', start = NULL, msg = %s
                    WHERE comm_id = 1''',
                 [msg])
    conn.commit()

def cron_copy(conn):
    '''Normal processing. Take the next value from the source_cgm table,
determined by the min rtime where used is NO.  This is coded under the
assumption that it might run until we run out of fake entries in
source_cgm and that when we run out we want to clear out the fake
entries from latest_cgm, and reset everything, so the fake entries
will be copied repetitively forever.
    '''
    row = get_next_unused_test_value(conn)
    if row is None:
        # if row is none, reset and repeat
        reset_and_start_over(conn)
        row = get_next_unused_test_value(conn)
    # As long as we have *some* test values, the preceding code must find one
    (user_id, rtime, mgdl, trend, trend_code) = row
    # mark it as used
    curs = conn.cursor()
    curs.execute('''UPDATE loop_logic.source_cgm SET used = 'YES' WHERE rtime = %s''', [rtime])
    conn.commit()
    # Insert it into the real table, substituting current_timestamp() for rtime
    curs.execute('''INSERT INTO loop_logic.latest_cgm 
                    VALUES(NULL, 7, current_timestamp(), %s, %s, %s, 'fake')''',
                 [mgdl, trend, trend_code])
    conn.commit()
    # For debugging, let's put a message in the command table
    msg = f'copied {rtime}, {mgdl}, {trend}, {trend_code}'
    curs.execute('''UPDATE loop_logic.testing_command 
                    SET msg = %s 
                    WHERE comm_id = 1''',
                 [msg])
    conn.commit()

def get_next_unused_test_value(conn):
    '''search for the next value to copy, the min rtime among unused test
values. Returns a tuple from source_cgm: 

(user_id, rtime, mgdl, trend, trend_code)
'''
    curs = conn.cursor()
    curs.execute('''SELECT user_id, rtime, mgdl, trend, trend_code
                    FROM loop_logic.source_cgm
                    WHERE rtime = (SELECT min(rtime) 
                                   FROM loop_logic.source_cgm 
                                   WHERE used = 'NO');''')
    # one row or None if there are none left
    return curs.fetchone()
    

def reset_and_start_over(conn):
    '''Use this to clear the copied records to start over. This code is
similar to cron_start; if we wanted to put the current timestamp into
the command table whenever we restart, we could just use that
function.'''
    curs = conn.cursor()
    # delete the fake entries from latest_cgm
    curs.execute('''DELETE FROM loop_logic.latest_cgm WHERE status = 'fake'; ''')
    conn.commit()
    # update all the source entries, marking them unused
    curs.execute('''UPDATE loop_logic.source_cgm SET used = 'NO'; ''')
    conn.commit()
    

def run_as_cron():
    '''The processing we do when we run as a cron job: figure out what
needs doing, and dispatch to the appropriate function. We are either
getting a START command, getting a STOP command, or doing a regular
copy of the next test value.'''
    conn = dbi.connect()
    curs = conn.cursor()
    curs.execute('select command, status from loop_logic.testing_command where comm_id = 1')
    (command, status) = curs.fetchone()
    command = command.lower()
    if command == 'start':
        cron_start(conn)
        cron_copy(conn)
    elif command == 'stop':
        cron_stop(conn)
    elif command == 'restart':
        # a lot like start
        reset_and_start_over(conn)
        cron_copy(conn)
    elif command != '':
        msg = f'Did not understand this command: {command}. Expected "start" or "stop" without quotation marks'
        curs.execute('update loop_logic.testing_command set msg = % where comm_id = 1',
                     [msg])
    elif status == 'ON':
        # normal case when testing is ON
        cron_copy(conn)

if __name__ == '__main__': 
    run_as_cron()
