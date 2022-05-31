'''Migrates Hugh's records from the autoapp database to the insulin_carb_smoothed_2 table in the janice database'''

import sys
import collections
import cs304dbi as dbi
from datetime import datetime, timedelta
import date_ui

mysql_fmt = '%Y-%m-%d %H:%M:%S'

# this is the table we'll update. Change to janice.insulin_carb_smoothed_2 when we're ready
TABLE = 'janice.insulin_carb_smoothed_2'      # 'janice.mileva_test'
USER = 'Hugh'
USER_ID = 7

def debug(*args):
    print('debug', *args)

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
CRON.  The function returns the rtime where it started. Other
migration functions should start from that time.
    '''
    # first, read the last row, to determine the max rtime and the
    # current basal_amt_12, the latter because it has to be propagated
    # to all the new rows.
    curs = conn.cursor()
    # since we control the value of TABLE, using an f-string here is safe
    # Now that we're using Python 3.6 on this server, we can use f-strings. :-)
    curs.execute(f'''SELECT rtime, basal_amt_12 FROM {TABLE} 
                    WHERE rtime = (SELECT max(rtime) FROM {TABLE})''')
    max_rtime, basal_amt_12 = curs.fetchone()
    debug(f'max rtime in {TABLE}', max_rtime)
    if basal_amt_12 is None:
        raise Exception('basal_amt_12 is NULL for row with rtime = {}'.format(rtime))
    now = date_ui.to_rtime(datetime.now())
    rtime = max_rtime + timedelta(minutes=5)
    debug(f'fill_forward: inserting rows into {TABLE} starting at', rtime, 'ending at', now)
    insert = ("INSERT INTO {TABLE}(rtime, user, basal_amt_12) values(%s, '{USER}', {basal_amt_12})"
              .format(TABLE=TABLE, USER=USER, basal_amt_12=basal_amt_12))
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
        # We need to look back
        debug('special case for start_time > most recent')
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

# 5/19/2022
def actual_basal(conn, start_time):
    '''Combines the programmed basal with the command table to determine
the actual basal rate. This duplicates the work that is in basal_hour,
but basal_hour is summarized at the end of the hour, and if we want to
base our predictions on up-to-the-minute data, we need to do this ourselves. 

See additional info in this document: 
https://docs.google.com/document/d/1UBp8VDckHNzqjorcJNgkYaJXF6iR5CeluGQ3VB_GKkE/edit#
'''
    curs = dbi.dict_cursor(conn)
    # we need to go back far enough that there's at least one
    # cancel_temporary_basal preceding the start_time, so we do that with a subquery

    # If we go back *too* far, to the beginning of the data, there
    # will be no prior 'cancel_temp_basal' command, in which case we
    # want *all* the data. So we use ifnull() to get zero for the minimum command.
    curs.execute('''SELECT date, type, ratio, duration FROM autoapp.commands 
                    LEFT OUTER JOIN autoapp.commands_temporary_basal_data USING (command_id)
                    WHERE user_id = %s and command_id >= 
                         (SELECT ifnull(max(command_id),0) FROM autoapp.commands 
                          WHERE type = 'cancel_temporary_basal' and date < %s)
                    AND type in ('suspend','temporary_basal','cancel_temporary_basal')
                    AND state = 'done'; ''',
                 [USER_ID, start_time])
    commands = curs.fetchall()
    debug('there are {} commands to process since {}'.format(len(commands), start_time))
    for c in commands:
        debug(c)
    ## Now the real code
    rtime = date_ui.to_rtime(start_time)
    now = datetime.now()
    # programmed values
    programmed = programmed_basal(conn, start_time)
    debug('there are {} programmed basal'.format(len(programmed)))
    for p in programmed:
        debug(p)
    return merge_time_queues(start_time, now, programmed, commands)

def migrate_basal_12(conn, start_time):
    '''Computes actual (hourly) basal rate for each 5-minutes time step
and stores basal_amt_12 in each row.'''
    curs = conn.cursor()
    basal_rates = actual_basal(conn, start_time)
    twelfth = 1.0/12.0
    update = '''UPDATE {} SET basal_amt_12 = %s 
                WHERE rtime = %s and user = \'{}\'; '''.format(TABLE, USER)
    debug('update sql', update)
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
        raise ValueError('no programmed basal rates')
    if len(commands) == 0:
        raise ValueError('no commands')

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
        debug('first 4 programmed rates: ',programmed_basal_rates[0:4])
        raise ValueError('programmed basal had no past values')

    temp_basal = None           # invisible state variable
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
        debug('commands had no past values; first is: ',commands[0])
        debug('assuming no temp basal')
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
    for p in prog2:
        print(p)
    print('comms1')
    for c in comms1:
        print(c)

    return merge_time_queues('2022-01-02', '2022-01-02 6:00:00', prog2, comms1)

# ================================================================


def test_programmed_basal(conn, printp=True):
    vals = programmed_basal(conn, '2022-04-19')
    for d in vals:
        print(str(d['rtime'])+"\t"+str(d['programmed_basal_rate']))
    return vals



def bolus_import(conn, start_rtime):
    '''Migrates the bolus table from autoapp. This is tricky because of the Extended boluses. 

Note that extended boluses are on top of the basal_amt, so we have a
new column: extended_bolus_amt_12

An S entry just means a simple bolus. 
    (But what does a non-zero duration mean? See #57 among many others)

An E entry is recorded via extended_bolus_amt_12
  (when the duration ends, the extended_bolus_amt_12 should go to zero)
  Also, some E entries are zero. So extended_bolus_amt_12 goes to zero then, correct?
  bolus 95 is E for value zero and duration zero. What does that mean?

A DS entry is, I think, the same as an S entry, but maybe is paired with a DE entry?
An DE entry is when the extended dose (changed basal) ends. Sometimes, it's paired with a DS entry.
  For example:
|     1062 |       7 | 2021-12-27 21:44:00 | DS   | 1.4000000000000001 |        0 | 2021-12-27 21:56:26 |
|     1065 |       7 | 2021-12-27 23:44:00 | DE   | 1.4000000000000001 |      120 | 2021-12-27 23:56:24 |

Why are bolus ids going up when date goes down?
Why are some bolus ids missing?

    '''
    curs = conn.cursor()
    # S entries first

    # Note, there are 13 rows where the date in the
    # bolus table equals the date in the basal_hour table. Are those
    # incompatible?

    # Note that because the rows should now exist, we have to use the
    # on duplicate key trick, because replace will *delete* any
    # existing row and replace it. We don't want that. We want to
    # update it if it's already there, and it will be. There may be a more
    # efficient way to do this, but it works.
    curs.execute('''insert into {}( rtime, bolus_type, total_bolus_volume)
                    select 
                        janice.date5f(date),
                        'S',
                        if(value='', NULL, value)
                    from autoapp.bolus
                    where user_id = 7 and type = 'S' and date >= %s
                    on duplicate key update 
                        total_bolus_volume = values(total_bolus_volume)'''.format(TABLE),
                 [start_rtime])
    conn.commit()
    # E entries

    # These dribble out the insulin over time, like the basal, but
    # it's on *top* of the basal. So, we need a new column: extended_bolus_amt_12.
    # data is value (an amount) and a duration. 

    # This needs to set all new rows (>= start_rtime), but those rows
    # might be affected by extended boluses that started in the recent
    # past. So we compute when the extended bolus should end and
    # check.  I worry a bit about efficiency here: there should be a
    # way to focus on the relevant rows: as we get to thousands of
    # rows, we don't want to be computing when an extended bolus ended
    # from some event last month or last year.

    src = conn.cursor()
    # bolus_id > 1100 and
    n = src.execute('''select janice.date5f(date) as rtime, value as extended_bolus_total, duration
                       from autoapp.bolus 
                       where user_id = 7 and type = 'E' 
                       AND duration > 0 and date_add(date, interval duration minute) >= %s;''',
                    [start_rtime])
    debug('updating with {} E events from bolus table'.format(n))
    dst = conn.cursor()
    for row in src.fetchall():
        rtime, volume, duration = row
        end_time = rtime + timedelta(minutes=duration)

        # there are 12 entries per hour, so if time is given in
        # minutes, say V units in 120 minutes, that's 120/12 drips and
        # each drip is V / (120/12)
        extended_bolus_amt_12 = volume / (duration/12)

        dst.execute('''UPDATE {} SET extended_bolus_amt_12 = %s 
                       WHERE user='{}' AND %s <= rtime and rtime <= %s'''.format(TABLE,USER),
                      [extended_bolus_amt_12, rtime, end_time])
    conn.commit()
        
    # DS events. Treating them just like S, for now.
    n = curs.execute('''insert into {}( rtime, bolus_type, total_bolus_volume)
                    select 
                        janice.date5f(date),
                        'DS',
                        if(value='', NULL, value)
                    from autoapp.bolus
                    where user_id = 7 and type = 'DS' and date >= %s
                    on duplicate key update 
                        total_bolus_volume = values(total_bolus_volume)'''.format(TABLE),
                     [start_rtime])
    debug('updated with {} DS events from bolus table'.format(n))
    conn.commit()

    # DE events. Need to go back and drip out the insulin over the
    # given duration, similar to E type boluses.
    src = conn.cursor()
    n = src.execute('''select janice.date5f(date) as rtime, value as extended_bolus_total, duration
                       from autoapp.bolus 
                       where user_id = 7 and type = 'DE' 
                       AND duration > 0 and date_add(date, interval duration minute) >= %s;''',
                    [start_rtime])
    debug('updating with {} DE events from bolus table'.format(n))
    dst = conn.cursor()
    for row in src.fetchall():
        rtime, volume, duration = row
        start_time = rtime - timedelta(minutes=duration)

        # there are 12 entries per hour, so if time is given in
        # minutes, say V units in 120 minutes, that's 120/12 drips and
        # each drip is V / (120/12)
        extended_bolus_amt_12 = volume / (duration/12)

        dst.execute('''UPDATE {} SET extended_bolus_amt_12 = %s 
                       WHERE user='{}' AND %s <= rtime and rtime <= %s'''.format(TABLE,USER),
                      [extended_bolus_amt_12, start_time, rtime])
    conn.commit()
    




## ================================================================

def carbohydrate_import(conn, start_rtime):
    curs = conn.cursor()
    num_rows = curs.execute(

    '''INSERT INTO {}(rtime, carbs) 
                               SELECT janice.date5f(date) as rtime, value as carbs
                               FROM autoapp.carbohydrate
                               WHERE date >= %s
                               ON DUPLICATE KEY UPDATE carbs = values(carbs)'''.format(TABLE),
                            [start_rtime])
    debug('inserted {} carb entries'.format(num_rows))
    

# TBD
def glucose_import(conn, start_rtime):
    debug('glucose_import is not yet implemented')
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
    debug('migrating cgm data starting at ', start_cgm)
    curs.execute('''UPDATE insulin_carb_smoothed_2 AS ics 
                        INNER JOIN realtime_cgm2 AS rt USING (rtime)
                    SET ics.cgm = rt.mgdl
                    WHERE rtime >= %s''',
                 [start_cgm])
    conn.commit()
                    

# ================================================================
# this is the main function

def migrate_all(conn=None, verbose=False, alt_start_time=None):
    '''This is the function that should, eventually, be called from a cron job every 5 minutes.'''
    if conn is None:
        conn = dbi.connect()
    if verbose: print('starting')
    max_start_rtime = fill_forward(conn)
    start_rtime = alt_start_time or max_start_rtime
    if verbose: print('start_rtime is {}'.format(start_rtime))
    # basal hour is obsolete because it might be behind by up to an hour
    # if verbose: print('basal_hour_import_2')
    # basal_hour_import_2(conn, start_rtime)
    if verbose: print('migrate_basal_12')
    migrate_basal_12(conn, start_rtime)
    # this is obsolete
    # if verbose: print('temp basal state')
    # temp_basal_state_import_incremental(conn, start_rtime)
    if verbose: print('bolus')
    bolus_import(conn, start_rtime)
    if verbose: print('carbohydrate')
    carbohydrate_import(conn, start_rtime)
    if verbose: print('glucose')
    glucose_import(conn, start_rtime)
    if verbose: print('done')

def pm_data(conn, since):
    '''print all the migrated data we need for the predictive model,
namely basal_amt_12, bolus, carbs, and bg. Copy/paste into a
spreadsheet to share with Janice and Mileva

    '''
    curs = dbi.cursor(conn)
    n = curs.execute('''SELECT rtime, round(basal_amt_12*12,1) as basal_rate, 
                        bolus_type, total_bolus_volume, extended_bolus_amt_12
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
    if len(sys.argv) > 1 and sys.argv[1] == 'cron':
        migrate_all(conn, verbose=True)
        migrate_cgm(conn)
        sys.exit()
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
    
