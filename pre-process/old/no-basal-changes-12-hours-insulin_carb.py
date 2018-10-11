#!/usr/bin/env python

import sys
import dbconn2
import MySQLdb
from datetime import datetime, timedelta
import decimal                  # some MySQL types are returned as type decimal

SERVER = 'hughnew'              # hughnew versus tempest
EPOCH_FORMAT = '%Y-%m-%d %H:%M:%S'
RTIME_FORMAT = '%Y-%m-%d %H:%M'
US_FORMAT = '%m/%d %H:%M'

def get_dsn():
    return dbconn2.read_cnf()

def get_conn(dsn=get_dsn()):
    return dbconn2.connect(dsn)

def row_generator(query,conn=get_conn(),pipeIn=None,year=None,month=None,day=None):
    if pipeIn is None:
        curs = conn.cursor(MySQLdb.cursors.DictCursor) # results as Dictionaries
        if year is not None and month is not None and day is not None:
            query += ' WHERE year(date_time) = {year} and month(date_time) = {month} and day(date_time)={day}'.format(year=year, month=month, day=day)
        elif year is not None:
            query += ' WHERE year(date_time) = {year}'.format(year=year)
        curs.execute(query)
        while True:
            row = curs.fetchone()
            if row is None:
                return
            yield row
    else:
        # substitute source
        for row in pipeIn:
            yield row

def no_basal_changes(time_delay=timedelta(hours=12)):
    gaps = []
    num_gaps = 0
    prev = None
    print 'Gaps between non-null values of basal_amt of more than {} in insulin_carb_grouped'.format(time_delay)
    for row in row_generator('SELECT basal_amt, date_time, rec_num FROM insulin_carb_grouped ORDER BY date_time ASC'):
        if row['basal_amt'] is None:
            continue
        if prev is None:
            prev = row
        if row['basal_amt'] is None or prev['basal_amt'] is None:
            raise Exception('NULL value got through')
        if (row['date_time'] - prev['date_time']) > time_delay:
            gaps.append(prev)
            num_gaps += 1
            print '{}: {} - {} = {}'.format(num_gaps,
                                            row['date_time'], prev['date_time'],
                                            row['date_time'] - prev['date_time'])
        prev = row
    return gaps

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print '''usage: {} report|update timedelta
example: {} 12
report finds gaps where there are no basal change for N hours
update modifies the insulin_carb_grouped table to mark the gaps'''.format(sys.argv[0],sys.argv[0])
    else:
        no_basal_changes(timedelta(hours=int(sys.argv[1])))
        
