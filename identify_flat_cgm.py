'''Identify rows of realtime_cgm2 that where the cgm has not changed in N minutes.

Eventually, we'll replace these with NULL, because they probably represent missing data.

'''

import os                       # for path.join
import sys
import cs304dbi as dbi
from datetime import datetime, timedelta
import date_ui
import logging

USER = 'Hugh'
USER_ID = 7

def debugging():
    '''Run this in the Python REPL to turn on debug logging. The default is just error'''
    logging.basicConfig(level=logging.DEBUG)

def flat_areas(conn=None, flat_time=None):
    prev_cgm = None
    prev_rtime = None
    # counting streaks
    flat_streak_count = 0
    # current streak info
    flat_streak = False
    flat_long_streak = False
    flat_cgm = None
    flat_since = None

    # ready to loop
    curs = dbi.cursor(conn)
    # curs.execute('select rtime, mgdl from realtime_cgm2 where date(rtime) = "2022-04-05" ')
    curs.execute('select rtime, mgdl from realtime_cgm2 where year(rtime) = "2022" ')
    logging.debug('rtime', 'cgm', 'curr_cgm', 'cgm==curr_cgm', 'flat_since', 'flat_since is not None', 'rtime', 'flat_streak')
    for rtime,cgm in curs.fetchall():
        logging.debug(rtime, cgm, flat_cgm, flat_streak)
        if (cgm is not None and
            cgm != prev_cgm):
            logging.info(' not flat, so start again, possibly ending a streak')
            if flat_long_streak:
                flat_streak_count += 1
                diff = (rtime - flat_since)
                # print(f'streak {flat_streak_count} of {flat_cgm} since {flat_since} ending at {rtime}: {diff}')
                print(f'streak {flat_streak_count:3} of {flat_cgm:3} since {flat_since}: {diff}')
            # restart, but note current CGM
            flat_streak = False
            flat_long_streak = False
            flat_since = None
        elif not flat_streak:
            logging.info('starting a new streak')
            flat_streak = True
            flat_since = prev_rtime
            flat_cgm = prev_cgm
        elif (rtime - flat_since) > flat_time:
            logging.info(f'continuing a long streak, since {flat_since}')
            flat_long_streak = True
        # history
        prev_cgm, prev_rtime = cgm, rtime

if __name__ == '__main__': 
    conn = dbi.connect()
    # debugging()
    flat_areas(conn, flat_time = timedelta(minutes=60))
    
