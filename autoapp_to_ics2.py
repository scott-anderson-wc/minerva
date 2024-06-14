'''Migrates Hugh's records from the autoapp database to the insulin_carb_smoothed_2 table in the janice database'''

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

def fill_forward(conn):
    '''The migration functions will assume that the ICS2 table has all the
necessary rows, so we can do the updates using the SQL UPDATE
statement rather than mess with REPLACE or INSERT ON DUPLICATE
KEY. This function establishes that precondition. All the functions
below can call this function first. It's idempotent, so calling it
unnecessarily is fine. Soon, we'll set this up as to be invoked via
CRON.  The function returns the rtime where it started. However, other
migration functions should start from autoapp.last_update.date. See
get_migration_time().

    '''
    # first, read the last row, to determine the max rtime
    curs = conn.cursor()
    # since we control the value of TABLE, using an f-string here is safe
    # Now that we're using Python 3.6 on this server, we can use f-strings. :-)
    curs.execute(f'''SELECT max(rtime) FROM {TABLE}''')
    max_rtime = curs.fetchone()[0]
    logging.debug(f'max rtime in {TABLE}: {max_rtime}')
    now = date_ui.to_rtime(datetime.now())
    rtime = max_rtime + timedelta(minutes=5)
    # this part needs to be idempotent, particularly when we are testing, so
    # I added the ON DUPLICATE KEY no-op
    logging.debug(f'fill_forward: inserting rows into {TABLE} starting at {rtime} ending at {now}')
    insert = ("""INSERT INTO {TABLE}(rtime, user) values(%s, '{USER}')
                 ON DUPLICATE KEY UPDATE user=user; """
              .format(TABLE=TABLE, USER=USER))
    while rtime < now:
        curs.execute(insert, [rtime])
        rtime += timedelta(minutes=5)
    conn.commit()
    # all done, return the time to start migration
    return max_rtime
    

## ----------------------------- Migration ----------------------------------------

## This would be a nice example in a more advanced database course....

def programmed_basal(conn, start_time):
    '''Goes through all records in base_basal_profile, pulling out the
program as it changes, and creating rows consisting of
rtime,basal_rate.  We need to know the basal program from before the
start_time, so we grab all records after the last one before
start_time.

    '''
    output_rows = collections.deque([])

    def get_curr_programmed_rate(program, rtime):
        hour = rtime.hour
        field='basal_profile_'+str(hour)
        return program[field]

    def save_curr_programmed_rate(program, rtime):
        curr_rate = get_curr_programmed_rate(program, rtime)
        # debug('rtime is {}, rate is {}'.format(rtime, curr_rate))
        output_rows.append({'rtime': rtime, 'programmed_basal_rate': curr_rate})

    now = datetime.now()
    
    prog_curs = dbi.dict_cursor(conn)
    # fields are base_basal_profile_id, user_id, date, basal_profile_[0-23], server_date
    # used * because the 24 long column names are annoying.
    # Note that we have to reach back to get at least one before start_time.
    rows = prog_curs.execute('''SELECT * FROM autoapp.base_basal_profile 
                                WHERE base_basal_profile_id >= 
                                    (SELECT max(base_basal_profile_id) FROM autoapp.base_basal_profile
                                     WHERE date <= %s)''',
                             [start_time])
    if rows == 0:
        # oh dear. Special case for start_time > most recent
        # We need to look back to find the most recent programmed basal 
        loggin.debug('special case for start_time > most recent')
        prog_curs.execute('''SELECT * from autoapp.base_basal_profile 
                             WHERE base_basal_profile_id = (SELECT max(base_basal_profile_id) 
                                                            FROM autoapp.base_basal_profile)''')

    curr_prog = prog_curs.fetchone()
    # next_prog might be None if curr_prog is the last one.
    next_prog = prog_curs.fetchone()
    rtime = date_ui.to_rtime(start_time)
    save_curr_programmed_rate(curr_prog, rtime)
    while True:
        # rtime += timedelta(minutes=5)
        # temporarily switch to hourly
        rtime += timedelta(hours=1)
        # loop until rtime up to now. 
        if rtime > now:
            break
        if next_prog is not None and rtime >= next_prog['date']:
            # get the next program
            curr_prog = next_prog
            next_prog = prog_curs.fetchone()
        save_curr_programmed_rate(curr_prog, rtime)
    return list(output_rows)



'''1/13/2023 This needs to be re-written. We should use the basal_hour
data for anything older than an hour. The basal_hour will be accurate
for the hour it's listed. So if it says 1.2 on 1/13/2023 at 4:00, that
means that the basal rate is 1.2 starting at 4:00. 

We should use the real-time calculation for times past the basal hour:
determine the current programmed rate, check the command table for any
non-canceled temporary_basals, join with the
commands_temporary_basal_data table to determine the ratio and use
that.

For any past data, if our data is missing, we should use the
basal_hour data. Otherwise, trust our real-time calculation.

Very often, there will be a long gap of commands during the day when
Hugh is away from the phone that does the upload. Then he comes home
and syncs with the phone, and autoapp suddenly has a bunch of incoming
stuff. Then we have a lot to migrate, so we should use the basal_hour
for that data.

'''

'''Update on June 6, 2024. We were getting Exceptions in the code
below because there were no temp basal commands we could count
on. That could just be because the subquery should look for a
cancel_temporary_basal that is of state 'done'.  And maybe with
error=0. However, what if it's not able to find one in the last N
hours. What if N is 2, 10, 24? This worries me.

I added the clause "AND state = 'done'" to the subquery, but we need
to test this more thoroughly.

'''

# function new for June 2024; factored out from actual_basal, below, so
# we can test this 
def recent_temp_basal_commands(conn, start_time):
    '''Return a non-empty list of temp basal commands since the most
    recent cancel_temporary_basal prior to start_time. In practice,
    start_time will be roughly now, so there won't be any after that,
    but for the sake of testing this, we limit the result to commands
    whose update_timestamp precedes start_time.
    '''
    curs = dbi.dict_cursor(conn)
    # we need to go back far enough that there's at least one
    # cancel_temporary_basal preceding the start_time, so we do that with a subquery

    # If we go back *too* far, to the beginning of the data, there
    # will be no prior 'cancel_temp_basal' command, in which case we
    # want *all* the data. So we use ifnull() to get zero for the minimum command.
    curs.execute('''SELECT update_timestamp as 'date', type, ratio, duration FROM autoapp.commands 
                    LEFT OUTER JOIN autoapp.commands_temporary_basal_data USING (command_id)
                    WHERE user_id = %s and command_id >= 
                         (SELECT ifnull(max(command_id),0) FROM autoapp.commands 
                          WHERE type = 'cancel_temporary_basal'
                            AND state = 'done'
                            AND update_timestamp < %s)
                    AND type in ('suspend','temporary_basal','cancel_temporary_basal')
                    AND state = 'done'
                    AND update_timestamp <= %s; ''',
                 [USER_ID, start_time, start_time])
    commands = curs.fetchall()
    if len(commands) == 0:
        # having no commands is a problem because we need commands to
        # be sure whether temp basal is off (we need it to be off) so
        # we can determine the actual basal.
        raise Exception('no recent temp_basal commands at time {}'.format(start_time))
    logging.debug('there are {} commands to process since {}'.format(len(commands), start_time))
    for c in commands:
        logging.debug(dic2str(c))
    return commands
    
def dic2str(dic):
    '''by reaching in and doing str() of keys and values, values that
    are datetimes get converted to something more readable.'''
    val = '{'
    for k,v in dic.items():
        val += str(k)+': '+str(v)+', '
    val += '}'
    return val

def recent_temp_basal_commands_test(conn,
                                    test_start_date='2023-01-02',
                                    test_end_date='2024-06-11'):
    '''Try every minute in the given interval.'''
    st = date_ui.to_datetime(test_start_date)
    et = date_ui.to_datetime(test_end_date)
    dt = timedelta(minutes=1)
    while st < et:
        # the function raises an exception if it's ever empty, so it's
        # sufficient just to invoke the function
        recent_temp_basal_commands(conn, st)
        st += dt
        
# 5/19/2022
# Revised 6/11/2024 to use function above
def actual_basal(conn, start_time):
    '''Combines the programmed basal with the command table to determine
the actual basal rate. This duplicates the work that is in basal_hour,
but basal_hour is summarized at the end of the hour, and if we want to
base our predictions on up-to-the-minute data, we need to do this ourselves. 

See additional info in this document: 
https://docs.google.com/document/d/1UBp8VDckHNzqjorcJNgkYaJXF6iR5CeluGQ3VB_GKkE/edit#
'''
    commands = recent_temp_basal_commands(conn, start_time)
    ## Now the real code
    rtime = date_ui.to_rtime(start_time)
    now = datetime.now()
    # programmed values
    programmed = programmed_basal(conn, start_time)
    logging.debug('there are {} programmed basal'.format(len(programmed)))
    for p in programmed:
        logging.debug(str(p))
    return merge_time_queues(start_time, now, programmed, commands)

def actual_basal_test(conn,
                      test_start_date='2023-01-02',
                      test_end_date='2024-06-11'):
    '''Try every minute in the given interval.'''
    st = date_ui.to_datetime(test_start_date)
    et = date_ui.to_datetime(test_end_date)
    dt = timedelta(minutes=1)
    while st < et:
        # the function raises an exception if it's ever empty, so it's
        # sufficient just to invoke the function
        actual_basal(conn, st)
        st += dt
        

def migrate_basal_12(conn, start_time):
    '''Computes actual (hourly) basal rate for each 5-minutes time step
and stores basal_amt_12 in each row.'''
    curs = conn.cursor()
    basal_rates = actual_basal(conn, start_time)
    twelfth = 1.0/12.0
    update = '''UPDATE {} SET basal_amt_12 = %s 
                WHERE rtime = %s and user = \'{}\'; '''.format(TABLE, USER)
    logging.debug('update sql {}'.format(update))
    for row in basal_rates:
        curs.execute(update, [ row['actual basal']*twelfth, row['rtime'] ])
    conn.commit()
    # the return is nice for debugging. use print_rows() and
    # copy/paste to a spreadsheet to share with Janice
    return basal_rates

# 5/29/22
def merge_time_queues(start_time, stop_time, programmed_basal_rates, commands):
    '''returns a list of rtimes from start_time to stop_time and 'actual
basal' rates (in hourly units) taking into account two "queues" of
information: basal_rates are programmed hourly rates and commands are
temp basals (percentages or cancelations).'''
    start_rtime = date_ui.to_rtime(start_time)
    stop_rtime = date_ui.to_rtime(stop_time)
    rtime = start_rtime
    result = []
    ## queues always have *future* times or are empty, but they need
    ## to start with some *past* values so that we can set up the
    ## state variables.  We dequeue data when rtime passes the time
    ## for the first thing in the queue. If the queue becomes empty,
    ## state variable just continues forever.
    if len(programmed_basal_rates) == 0:
        raise ValueError('no programmed basal rates at time {}'.format(start_time))
    if len(commands) == 0:
        raise ValueError('no commands at time {}'.format(start_time))

    event = None                # one-time state variable

    programmed_rate = None      # invisible state variable
    def curr_programmed_rate():
        nonlocal programmed_rate
        nonlocal event
        while len(programmed_basal_rates) > 0 and rtime >= programmed_basal_rates[0]['rtime']:
            top = programmed_basal_rates.pop(0)
            if top['programmed_basal_rate'] != programmed_rate:
                event = 'change in programmed rate'
                programmed_rate = top['programmed_basal_rate']
        return programmed_rate

    # if start_time is well in the past (we're migrating a ton of old data), we might not
    # know what the state variable was at that time. So, we can 
    if curr_programmed_rate() is None:
        logging.debug('first 4 programmed rates: {}'.format(programmed_basal_rates[0:4]))
        raise ValueError('programmed basal had no past values')

    temp_basal = None           # invisible state variable. Value is 1.0 when no temp_basal.
    temp_basal_end_time = None  # invisible state variable
    def curr_temp_basal():
        nonlocal temp_basal
        nonlocal temp_basal_end_time
        nonlocal event
        if temp_basal_end_time and rtime >= temp_basal_end_time:
            # turn off temp basal after given duration
            temp_basal, temp_basal_end_time, event = 1.0, None, 'temp basal off'
        while len(commands) > 0 and rtime >= commands[0]['date']:
            top = commands.pop(0)
            # this will ignore any other commands
            if top['type'] == 'temporary_basal':
                event = 'command: temp basal on'
                temp_basal = top['ratio']/100.0
                temp_basal_end_time = top['date'] + timedelta(hours=top['duration'])
            elif top['type'] == 'cancel_temporary_basal':
                event = 'command: cancel temp basal'
                temp_basal = 1.0
        return temp_basal

    # if start_time is well in the past, we might not have any commands prior to the start time.
    # but I think that's okay.
    if curr_temp_basal() is None:
        logging.debug('commands had no past values; first is: {}'.format(commands[0]))
        logging.debug('assuming no temp basal')
        temp_basal = 1.0
        # raise ValueError('commands had no past values')

    # okay, state variables are set, and we're ready to go
    result = collections.deque([])
    while rtime <= stop_rtime:
        pr = curr_programmed_rate()
        tb = curr_temp_basal()
        ab = pr * tb 
        result.append({'rtime':rtime, 'actual basal': ab, 'event': event})
        event = ''
        rtime += timedelta(minutes=5)
    return list(result)
    
def print_rows(rows):
    keys = rows[0].keys()
    print('\t'.join(keys))
    for row in rows:
        # can I just use values?
        row_list = [ str(row[k]) for k in keys ]
        print('\t'.join(row_list))

def __test_merge_time_queues():
    prog1 = [ ['2022-01-01 23:00:00', 0.7],
               ['2022-01-02 1:00:00', 1.2],
               ['2022-01-02 2:00:00', 0.3]
               ]
    prog2 = [ {'rtime':date_ui.to_datetime(t[0]), 'programmed_basal_rate':t[1]}
              for t in prog1 ]

    # temp basals percentages are in 0-100
    # cols are date, command, ratio, duration 
    times3 = [ ['2022-01-01 23:30:00', 'cancel_temporary_basal', None, None ],
               ['2022-01-02 0:10:00', 'temporary_basal', 40, 1 ],
               ['2022-01-02 2:20:00','temporary_basal', 60, 1 ],
               ['2022-01-02 4:30:00','temporary_basal', 80, 1 ]
               ]
    comms1 = [ {'date': date_ui.to_datetime(t[0]),
                'type': t[1],
                'ratio': t[2],
                'duration': t[3] }
               for t in times3 ]

    print('prog2')
    print_rows(prog2)
    print('comms1')
    print_rows(comms1)
    for c in comms1:
        print(c)
    # this is looking at a 6-hour window, so 6*12 or 72 results
    merged = merge_time_queues('2022-01-02', '2022-01-02 6:00:00', prog2, comms1)
    print('merged',len(merged))
    print_rows(merged)
    return merged

# ================================================================


def test_programmed_basal(conn, printp=True):
    vals = programmed_basal(conn, '2022-04-19')
    for d in vals:
        print(str(d['rtime'])+"\t"+str(d['programmed_basal_rate']))
    return vals

# ================================================================

def bolus_import_s(conn, start_rtime, debugp=False):
    '''An S entry means just a simple bolus. But what does a non-zero
duration mean? See #57 among others.'''
    curs = conn.cursor()

    # Note, there are 13 rows where the date in the
    # bolus table equals the date in the basal_hour table. Are those
    # incompatible?

    # Note that because the rows should now exist, we have to use the
    # on duplicate key trick, because replace will *delete* any
    # existing row and replace it. We don't want that. We want to
    # update it if it's already there, and it will be. There may be a more
    # efficient way to do this, but it works.

    # Now that we have relevance_lag, this should capture S boluses in
    # the recent past. The ON DUPLICATE KEY code should make it
    # idempotent.
    nr = curs.execute('''insert into {}( rtime, bolus_type, total_bolus_volume)
                         select
                            janice.date5f(date),
                            type,
                            if(value='', NULL, value)
                        from autoapp.bolus
                        where user_id = 7 and type = 'S' and date >= %s
                        on duplicate key update 
                            bolus_type = values(bolus_type),
                            total_bolus_volume = values(total_bolus_volume)'''.format(TABLE),
                 [start_rtime])
    conn.commit()
    return nr

def bolus_import_s_test(conn, start_rtime):
    start_rtime = date_ui.to_rtime(start_rtime)
    curs = conn.cursor()
    nr = curs.execute('''select janice.date5f(date),type,if(value='', NULL, value)
                         from autoapp.bolus
                         where user_id = 7 and type = 'S' and date >= %s''',
                 [start_rtime])
    print('{} S boluses since {}'.format(nr, start_rtime))
    for row in curs.fetchall():
        print("\t".join(map(str,row)))
    nr = bolus_import_s(conn, start_rtime, debugp=True)
    print('result: {} rows modified'.format(nr))
    nr = curs.execute('''select rtime, bolus_type, total_bolus_volume
                         from {}
                         where bolus_type = 'S' and rtime >= %s'''.format(TABLE),
                      [start_rtime])
    print('{} S boluses since {}'.format(nr, start_rtime))
    for row in curs.fetchall():
        print("\t".join(map(str,row)))
    
def bolus_import_ds(conn, start_rtime, debugp=False):
    '''A DS entry is, I think, the same as an S entry, but maybe is paired
    with a DE entry?  '''
    # DS events. Treating them just like S, for now.
    curs = conn.cursor()
    # Again, the ON DUPLICATE KEY trick should make this idempotent
    # and do the right thing now that we have relevance_lag
    n = curs.execute('''insert into {}( rtime, bolus_type, total_bolus_volume)
                    select 
                        janice.date5f(date),
                        'DS',
                        if(value='', NULL, value)
                    from autoapp.bolus
                    where user_id = 7 and type = 'DS' and date >= %s
                    on duplicate key update 
                        bolus_type = values(bolus_type),
                        total_bolus_volume = values(total_bolus_volume)'''.format(TABLE),
                     [start_rtime])
    logging.debug('updated with {} DS events from bolus table'.format(n))
    conn.commit()

def bolus_import_ds_test(conn, start_rtime):
    start_rtime = date_ui.to_rtime(start_rtime)
    curs = conn.cursor()
    nr = curs.execute('''select janice.date5f(date),type,if(value='', NULL, value)
                         from autoapp.bolus
                         where user_id = 7 and type = 'DS' and date >= %s''',
                 [start_rtime])
    print('{} DS boluses since {}'.format(nr, start_rtime))
    for row in curs.fetchall():
        print("\t".join(map(str,row)))
    nr = bolus_import_ds(conn, start_rtime, debugp=True)
    print('result: {} rows modified'.format(nr))
    nr = curs.execute('''select rtime, bolus_type, total_bolus_volume
                         from {}
                         where bolus_type = 'DS' and rtime >= %s'''.format(TABLE),
                      [start_rtime])
    print('{} DS boluses since {}'.format(nr, start_rtime))
    for row in curs.fetchall():
        print("\t".join(map(str,row)))

def approx_equal(x, y, maxRelDiff = 0.0001):
    '''see https://randomascii.wordpress.com/2012/02/25/comparing-floating-point-numbers-2012-edition/
true if the numbers are within maxRelDiff of each other, default 0.01%'''
    diff = abs(x-y)
    x = abs(x)
    y = abs(y)
    larger = x if x > y else y
    return diff <= larger * maxRelDiff

    
# ================================================================

def extended_bolus_import(conn, start_rtime, debugp=False):
    '''because extended boluses aren't recorded in the bolus table until
they complete, we have to use a different approach. We'll look at the
extended_bolus_state table, and compute the start time of the extended
bolus from the date - progress_minutes and the duration from minutes.'''
    curs = dbi.cursor(conn)
    n = curs.execute('''SELECT * 
                        FROM (SELECT date  
                                     - interval progress_minutes minute as e_start,
                                    date, absolute_rate, minutes, progress_minutes
                              FROM autoapp.extended_bolus_state
                              WHERE user_id = 7) as tmp
                        WHERE e_start > %s'''.format(USER_ID),
                     [start_rtime])
    logging.debug('updating with {} extended bolus reports since {}'.format(n, start_rtime))
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

# still working on this 

def extended_bolus_import_test(conn, start_rtime):
    start_rtime = date_ui.to_rtime(start_rtime)
    curs = conn.cursor()
    nr = curs.execute('''select janice.date5f(date),type,if(value='', NULL, value), duration
                         from autoapp.bolus
                         where user_id = 7 and type in ('DE','E') and date >= %s''',
                 [start_rtime])
    print('{} extended boluses since {}'.format(nr, start_rtime))
    for row in curs.fetchall():
        print("\t".join(map(str,row)))
    # before updating the destination TABLE, let's null out the extended_bolus_amt_12
    curs.execute('update {} set extended_bolus_amt_12 = null where rtime >= %s'.format(TABLE),
                 [start_rtime])
    conn.commit()
    nr = extended_bolus_import(conn, start_rtime, debugp=True)
    print('result: {} rows modified'.format(nr))
    # find sum of these DE drips
    curs.execute('''select sum(value) from autoapp.bolus 
                    where user_id = 7 and type in ('DE','E') and date >= %s''',
                 [start_rtime])
    row = curs.fetchone()
    before_sum = row[0]
    print('those all sum to {}'.format(before_sum))
    # because the boluses extend over time, I'm going to get every row, so
    # we can see when they start/stop
    nr = curs.execute('''select rtime, bolus_type, extended_bolus_amt_12
                         from {}
                         where rtime >= %s and extended_bolus_amt_12 is not null'''.format(TABLE),
                      [start_rtime])
    print('{} extended boluses since {}'.format(nr, start_rtime))
    for row in curs.fetchall():
        print("\t".join(map(str,row)))
    # let's also print the sum. Unfortunately, this sum will also include E boluses. What to do....
    # for debugging, we'll go back and set all the extended_bolus_amt_12 to null at the top of this
    curs.execute('select sum(extended_bolus_amt_12) from {} where rtime >= %s'.format(TABLE),
                 [start_rtime])
    row = curs.fetchone()
    after_sum = row[0]
    print('those all sum to {}'.format(after_sum))
    # floating point equality: less than 0.01%
    print('are the sums approximately equal? {}'.format(approx_equal(before_sum, after_sum)))


# ================================================================


def bolus_import(conn, start_rtime, debugp=False):

    '''Migrates the bolus table from autoapp. 

An DE entry is when the extended dose (changed basal) ends. Sometimes, it's paired with a DS entry.
  For example:
|     1062 |       7 | 2021-12-27 21:44:00 | DS   | 1.4000000000000001 |        0 | 2021-12-27 21:56:26 |
|     1065 |       7 | 2021-12-27 23:44:00 | DE   | 1.4000000000000001 |      120 | 2021-12-27 23:56:24 |

Why are bolus ids going up when date goes down?
Why are some bolus ids missing?

    '''
    bolus_import_s(conn, start_rtime, debugp=debugp)
    bolus_import_ds(conn, start_rtime, debugp=debugp)
    # these are obsolete, replaced by extended_bolus_import
    # bolus_import_e(conn, start_rtime, debugp=debugp)
    # bolus_import_de(conn, start_rtime, debugp=debugp)
    extended_bolus_import(conn, start_rtime, debugp=debugp)
    # Added this to fix any carb_codes that were incorrect because the
    # bolus hadn't yet been recorded.
    update_carb_codes(conn, start_rtime, datetime.now(), debugp=debugp)

## ================================================================
## Carb import needs to also compute the carb code.

# This one is now obsolete
def old_carbohydrate_import(conn, start_rtime, debugp=False):
    curs = conn.cursor()
    # the ON DUPLICATE KEY makes this idempotent
    num_rows = curs.execute(
        '''INSERT INTO {}(rtime, carbs) 
           SELECT janice.date5f(date) as rtime, value as carbs
           FROM autoapp.carbohydrate
           WHERE date >= %s
           ON DUPLICATE KEY UPDATE carbs = values(carbs)'''.format(TABLE),
        [start_rtime])
    if debugp:
        logging.debug('inserted {} carb entries'.format(num_rows))

'''The rule is that carbs with insulin are a meal, where "with
insulin" means insulin within a 65 minute window before or after the
meal. If the insulin comes before the meal, this function will notice
it. However, if the insulin comes into the database *after* the carbs
are imported, the carbs will initially be categorized as
'rescue'. We'll have to fix that after the fact, when we import the
bolus info.

Nov 10, 2022
'''

# mean_name is also defined in iob2.py
from dynamic_insulin import meal_name

MEAL_INSULIN_TIME_INTERVAL = 30

def carbohydrate_import(conn, start_rtime, debugp=False):
    '''Gets all the recent carbs in autoapp, and for each, searches if
there has been recent boluses. If so, these are a meal and we compute
the meal_name and store that. Otherwise, these are rescue carbs and we
store that.'''
    curs = conn.cursor()
    nrows = curs.execute('''select janice.date5f(date) as rtime, value as carbs
                            from autoapp.carbohydrate
                            where date >= %s''',
                         [start_rtime])
    logging.debug(f'found {nrows} carbs to migrate')
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

def carbohydrate_import_test(conn, start_rtime):
    start_rtime = date_ui.to_rtime(start_rtime)
    curs = conn.cursor()
    nr = curs.execute('select date, value from autoapp.carbohydrate where date >= %s',
                 [start_rtime])
    print('{} carbs since {}'.format(nr, start_rtime))
    for row in curs.fetchall():
        print("\t".join(map(str,row)))
    curs.execute('select sum(value) from autoapp.carbohydrate where date >= %s',
                 [start_rtime])
    row = curs.fetchone()
    before_sum = row[0]
    print('summing to {}'.format(before_sum))
    carbohydrate_import(conn, start_rtime, debugp=True)
    nr = curs.execute('''SELECT rtime, carbs from {} 
                          WHERE rtime >= %s and carbs is not null'''.format(TABLE),
                      [start_rtime])
    print('{} carbs since {}'.format(nr, start_rtime))
    for row in curs.fetchall():
        print("\t".join(map(str,row)))
    curs.execute('select sum(carbs) from {} where rtime >= %s'.format(TABLE),
                 [start_rtime])
    row = curs.fetchone()
    after_sum = row[0]
    print('summing to {}'.format(after_sum))
    print('are sums equal? {}'.format(before_sum == after_sum))
    

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

# TBD
def glucose_import(conn, start_rtime):
    logging.debug('glucose_import is not yet implemented')
    return
    curs = conn.cursor()
    curs.execute('''INSERT INTO {}(rtime, carbs) 
                    SELECT janice.date5f(date) as rtime, value as carbs
                    FROM autoapp.carbohydrate
                    WHERE date >= %s
                    ON DUPLICATE KEY UPDATE carbs = values(carbs)'''.format(TABLE),
                 [start_rtime])
    
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
# this is the main function

def migrate_all(conn=None, verbose=False, alt_start_time=None):
    '''This is the function that should, eventually, be called from a cron job every 5 minutes.'''
    if conn is None:
        conn = dbi.connect()
    logging.info('starting')
    if verbose: print('starting')
    fill_forward(conn)
    prev_update, last_update = get_migration_time(conn)
    if prev_update is None:
        if verbose:
            print('bailing because no updates')
        return
    start_rtime = alt_start_time or prev_update
    logging.info(f'start rtime is {start_rtime}')
    if verbose: print('start_rtime is {}'.format(start_rtime))
    # basal hour is obsolete because it might be behind by up to an hour
    # if verbose: print('basal_hour_import_2')
    # basal_hour_import_2(conn, start_rtime)
    logging.info('migrate_basal_12')
    if verbose: print('migrate_basal_12')
    migrate_basal_12(conn, start_rtime)
    # this is obsolete
    # if verbose: print('temp basal state')
    # temp_basal_state_import_incremental(conn, start_rtime)
    logging.info('bolus')
    if verbose: print('bolus')
    bolus_import(conn, start_rtime)
    logging.info('carbohydrate')
    if verbose: print('carbohydrate')
    carbohydrate_import(conn, start_rtime)
    logging.info('glucose')
    if verbose: print('glucose')
    glucose_import(conn, start_rtime)
    logging.info('storing update time')
    if verbose: print('logging update time')
    set_migration_time(conn, prev_update, last_update)
    logging.info('done')
    if verbose: print('done')

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
    if len(sys.argv) > 1 and sys.argv[1] == 'obsolete':
        start_rtime = fill_forward(conn)
        # backup by a day, so we can see whether the algorithm is terrible
        # when it's incremental. Because it *is* terrible when it's
        # running from 9/22/2021. If it's just 24 hours, the time is
        # negligible. When it's 100 days, it takes a long time.
        start_rtime -= timedelta(days=100)
        print('start rtime', start_rtime)
        print('basal_hour_import_2')
        basal_hour_import_2(conn, start_rtime)
        print('temp basal state')
        temp_basal_state_import_incremental(conn, start_rtime)
        '''
    I'm going to print entries where I think something weird is going on:

    * S with non-zero duration (300+)
    * E with zero duration (only 1)
    * DE with zero duration (none)
    '''
        # non_zero_duration_S_boluses(conn)
        # zero_duration_E_boluses(conn)
        # simultaneous_bolus_and_basal(conn)
        # basal_import(conn, start_rtime)
        print('bolus_import')
        bolus_import(conn, start_rtime)
        # temp_basal_state_import_incremental(conn, start_rtime)
        print('carbs')
        carbohydrate_import(conn, start_rtime)
        print('glucose')
        glucose_import(conn, start_rtime)
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
