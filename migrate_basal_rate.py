'''New implementation as of June 2024.

1. The main function is migrate_basal_12. It takes 3 arguments, conn,
start_time and end_time.

The start_time is the same as for most of our data: the last time that
there was new data, or the previous update time. Since the cron job
runs every minute, start_time will typically be in the very recent
past. Functions may need to look back further to get the data they
actually need. For example, we'll need to look for temp_basal commands
that precede start_time.

The end_time will be now() when run as a cron job. When we are
catching up or debugging, the end_time may well be different. To avoid
algorithms running amok, we will need to limit their data to before
end_time.

2. migrate_basal_12 calls a function actual_basal that returns a list
of relevant interesting events in the history of the basal rate. It
uses that list of events (basal_rates) to compute a sequence of
basal_rate_12 values that it fills into ICS.

3. actual_basal(conn, start_time, end_time) finds two sequences of
information:

   A. it finds the most recent cancel_temp_basal that precedes
      start_time, and finds all status=done commands from then until end_time.

   B. it finds all programmed rates that span the time interval for
      part A and start_time to end_time. Actually, we don't need to be
      that general. These programmed events always fall on the hour,
      so rather than a general merge() function, we can just have an
      array of 24 programmed rates. It calls programmed_rates(conn,
      start_time, end_time) to get that array.

actual_basal then creates a list of rtimes in the given interval and
their associated basal_rate. These are all at 5-minute intervals,
suitable for storing into the database. Actually, the function returns
a generator, which we can use for debugging or for feeding into
migrate_basal_12().

Janice pointed out (6/18/2024) that we only need the more elaborate
algorithm for the up-to-the-minute basal rate for the predictive
model. For older data, the data in basal_hour will be fine. However,
it occurs to me that if we want to use past data for learning, we
probably should go to the extra effort to use the more elaborate
algorithm to compute basal rate, so that the past data will be more
representative of the data that we want to use for prediction. So,
maybe I'll write the code to always use the elaborate algorithm.

I did a lot of testing using a particular example. See writeup here:

https://docs.google.com/document/d/1Ydvw3M2tk5zbqBDY9Zj69yuavBJxWKUqahkNdAOjZnE/edit

test_date1 = '2024-06-15 23:00'
test_date2 = '2024-06-16 04:00'

The computation on this test interval worked as of 6/18/2024.

'''

import random
import cs304dbi as dbi
from datetime import datetime, timedelta
import date_ui
import logging

USER_ID = 7

def migrate_basal_12(conn, start_time, end_time=date_ui.to_rtime(datetime.now())):
    '''update the database table insulin_carb_smoothed_2 with the
    actual basal rates for the given time interval.
    '''
    start_time = date_ui.to_rtime(start_time)
    end_time = date_ui.to_rtime(end_time)
    logging.info(f'migrate_basal_12 from {start_time} to {end_time}')
    curs = dbi.cursor(conn)
    try:
        for update in actual_basal(conn, start_time, end_time):
            # this shouldn't happen
            if update['basal_amt_12'] is None:
                logging.error(f'''ERROR: got a NULL basal_amt_12 for {update['rtime']}''')
            curs.execute('''UPDATE insulin_carb_smoothed_2
                            SET basal_amt = %s,
                                basal_amt_12 = %s,
                                notes = if(isnull(notes),%s,concat(notes,%s))
                            WHERE rtime = %s''',
                         [update['basal_amt'],
                          update['basal_amt_12'],
                          update['notes'],
                          update['notes'],
                          update['rtime']])
        conn.commit()
    except Exception as err:
        msg = repr(err)
        logging.error(f'ERROR! {msg} in migrate_basal_12 for inputs {start_time} and {end_time}')
        # raise err


def actual_basal(conn, start_time, end_time):
    '''Generator for a sequence of dictionaries, each with keys rtime,
    basal_rate, notes. The list is sorted by rtime.'''
    pr = programmed_rates_array(conn, start_time, end_time)
    rc = recent_temp_basal_commands(conn, start_time, end_time)
    # iterate from start_time to end_time, keeping track of current
    # factor (temp basal or suspend) and the programmed time, which
    # changes on the hour.
    try:
        start_time = date_ui.to_rtime(start_time)
        end_time = date_ui.to_rtime(end_time)
        # state variables
        rtime = start_time
        factor = 1.0
        temp_basal_end_time = None 
        rate = pr[rtime.hour]
        while rtime < end_time:
            notes = ''
            if rtime.minute == 0:
                rate = pr[rtime.hour]
            while len(rc) > 0 and rtime > rc[0]['date']:
                # process any commands that happened in the last 5 minutes
                # or prior to beginning this loop
                comm = rc.pop(0)
                if comm['type'] == 'cancel_temporary_basal':
                    factor, temp_basal_end_time = 1.0, None
                    notes += ' cancel;'
                if comm['type'] == 'temporary_basal':
                    ratio = comm['ratio']
                    factor = ratio/100.0
                    temp_basal_end_time = (date_ui.to_datetime(comm['date']) +
                                           timedelta(hours=comm['duration']))
                    notes += f' temp_basal {ratio};'
                if comm['type'] == 'suspend':
                    factor = 0.0
                    end_temp_basal = None
                    notes += ' suspend;'
            # programmed end of temp_basal
            if temp_basal_end_time is not None and rtime >= temp_basal_end_time:
                factor, temp_basal_end_time = 1.0, None
                notes += ' end temp'
            # Finally, compute the result.  I decided to round the
            # basal_amt to 2 decimal places, for readability. The
            # basal_amt_12 could probably be harmlessly rounded to 4
            # places.  What probably *should* happen is that they
            # should be represented as integers and only floated when
            # used in computations.
            yield {'rtime': rtime,
                   'basal_amt': round(rate*factor,2),
                   'basal_amt_12': rate*factor/12.0,
                   'notes': notes}
            # advance time by 5 minutes
            rtime += timedelta(minutes=5)
    except Exception as err:
        msg = repr(err)
        logging.error(f'ERROR! {msg} in actual_basal for inputs {start_time} and {end_time}')
        # raise err

def programmed_rates_array(conn, start_time, end_time):
    '''return an array of 24 values, where entry i is the programmed
    rate at hour i (e.g. 0 is midnight to 1am). Only the start_time is
    used. We find the program that was in effect at the start_time.'''
    try:
        curs = dbi.dict_cursor(conn)
        # most recent profile preceding end_time.
        nrows = curs.execute('''SELECT * FROM autoapp.base_basal_profile 
                                WHERE base_basal_profile_id >= 
                                   (SELECT max(base_basal_profile_id) FROM autoapp.base_basal_profile
                                    WHERE date <= %s)''',
                             [start_time])
        if nrows == 0:
            logging.debug(f'''ERROR! No programmed rates
                              between start_time ({start_time}) and end_time ({end_time})''')
            # replace it with the most recent profile, period
            curs.execute('''SELECT * from autoapp.base_basal_profile 
                            WHERE base_basal_profile_id = (SELECT max(base_basal_profile_id) 
                                                       FROM autoapp.base_basal_profile)''')
        # necessarily exactly one row
        row = curs.fetchone()
        prof_id = row['base_basal_profile_id']
        array = [ 0 for i in range(24) ]
        for i in range(24):
            array[i] = row[f'basal_profile_{i}']
        return array
    except Exception as err:
        msg = repr(err)
        logging.error(f'ERROR! {msg} in programmed_rates_array for inputs {start_time} and {end_time}')
        # raise err

def recent_temp_basal_commands(conn, start_time, end_time):
    '''Return a non-empty list of temp basal commands since the most
    recent cancel_temporary_basal prior to start_time. In practice,
    start_time will be roughly now, so there won't be any after that,
    but for the sake of testing this, we limit the result to commands
    whose update_timestamp precedes start_time. The keys of each are

    date, type, ratio, duration
    '''
    try:
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
                     [USER_ID, start_time, end_time])
        commands = curs.fetchall()
        if len(commands) == 0:
            # having no commands is a problem because we need commands to
            # be sure whether temp basal is off (we need it to be off) so
            # we can determine the actual basal.
            logging.error(f'ERROR! no recent temp_basal commands at time {start_time}')
        logging.debug('there are {} commands to process since {}'.format(len(commands), start_time))
        for c in commands:
            logging.debug(dic2str(c))
        return commands
    except Exception as err:
        msg = repr(err)
        logging.error(f'ERROR! {msg} in recent_temp_basal_commands for inputs {start_time} and {end_time}')
        # raise err


def dic2str(dic):
    '''by reaching in and doing str() of keys and values, values that
    are datetimes get converted to something more readable.'''
    pairs = [ f'{k}: {v}' for k,v in dic.items() ]
    return '{ '+','.join(pairs)+' }'

def test_dates(start_date = '2023-01-01', end_date='2024-06-18', per_day=12):
    '''generator for a bunch of test datetimes in the given
    interval. Every date in the range is tested per_day times.'''
    start_date = date_ui.to_datetime(start_date)
    end_date = date_ui.to_datetime(end_date)
    test_date = start_date.replace(hour=0, minute=0, second=0)
    while test_date < end_date:
        for i in range(12):
            test_time = test_date + timedelta(minutes=random.randint(0, 60*24))
            yield test_time
        test_date += timedelta(days=1)


def programmed_rates_array_test(conn, start_time='2023-01-01', end_time='2024-06-18'):
    # try a dozen random times every day between start_time and end time
    # this test was passed on 6/18/2024
    for date in test_dates(start_time, end_time):
        print(f'testing {date}')
        programmed_rates_array(conn, date, None)


def recent_temp_basal_commands_test(conn, start_time='2023-01-01', end_time='2024-06-18'):
    # try a dozen random times every day between start_time and end time, with 
    # random time intervals
    # this test was passed on 6/18/2024
    for test_start in test_dates(start_time, end_time):
        # most of the time, the interval will be short, except for
        # (rare) outages, so let's test random intervals between 1
        # minute and 30 minutes.
        test_end = test_start + timedelta(minutes=random.randint(1,30))
        print(f'testing {test_start} to {test_end}')
        recent_temp_basal_commands(conn, test_start, test_end)

def actual_basal_test(conn, start_time='2023-01-01', end_time='2024-06-18'):
    # try a dozen random times every day between start_time and end time, with 
    # random time intervals
    for test_start in test_dates(start_time, end_time):
        # most of the time, the interval will be short, except for
        # (rare) outages, so let's test random intervals between 1
        # minute and 30 minutes.
        test_end = test_start + timedelta(minutes=random.randint(1,30))
        print(f'testing {test_start} to {test_end}')
        # because actual_basal is a generator, we have to loop over
        # all its values to be sure it doesn't get an error.
        for val in actual_basal(conn, test_start, test_end):
            print(val)

test_date1 = '2024-06-15 23:00'
test_date2 = '2024-06-16 04:00'

