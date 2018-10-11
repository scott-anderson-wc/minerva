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
    for row in row_generator('SELECT mgdl, date_time, rec_num FROM cgm_2 ORDER BY date_time ASC'):
        if prev == None:
            prev = row
        if row['mgdl'] != prev['mgdl']:
            prev = row
        if (row['date_time'] - prev['date_time']) > time_delay:
            gaps.append(prev)
            num_gaps += 1
            print '{}: {} - {} = {}'.format(num_gaps,
                                            row['date_time'], prev['date_time'],
                                            row['date_time'] - prev['date_time'])
    return gaps

def longest_no_basal_changes(time_delay=timedelta(hours=12)):
    gaps = []
    num_gaps = 0
    prev = None
    for row in row_generator('SELECT mgdl, date_time, rec_num FROM cgm_2 ORDER BY date_time ASC'):
        if prev == None:
            prev = row
        if row['mgdl'] != prev['mgdl']:
            prev = row
        if (row['date_time'] - prev['date_time']) > time_delay:
            gaps.append(prev)
            num_gaps += 1
            print '{}: {} - {} = {}'.format(num_gaps,
                                            row['date_time'], prev['date_time'],
                                            row['date_time'] - prev['date_time'])
    return gaps

if __name__ == '__main__':
    no_basal_changes(timedelta(hours=3))
    
            
