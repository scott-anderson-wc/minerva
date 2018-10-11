#!/usr/bin/env python

import sys
import dbconn2
import MySQLdb
from datetime import datetime, timedelta

def get_dsn():
    return dbconn2.read_cnf()

def get_conn(dsn=get_dsn()):
    return dbconn2.connect(dsn)

def row_generator(query,conn=get_conn()):
    curs = conn.cursor(MySQLdb.cursors.DictCursor) # results as Dictionaries
    curs.execute(query)
    while True:
        row = curs.fetchone()
        if row is None:
            return
        yield row

def no_basal_changes(time_delay=timedelta(hours=12),update=False):
    gaps = []
    num_gaps = 0
    prev = None
    if not update:
        print 'Gaps between non-null values of basal_amt of more than {} in insulin_carb_2'.format(time_delay)
        print 'gap |   rec_nums   | later timestamp - earlier timestamp | time diffence'
        print '123 | 12345678 | 123456789012345 - 12345678901234567 | 1234567890123'
    conn = get_conn()
    curs2 = conn.cursor()
    for row in row_generator('SELECT basal_amt, date_time, rec_num FROM insulin_carb_2 ORDER BY date_time ASC'):
        if row['basal_amt'] is None:
            continue
        if prev is None:
            prev = row
        if row['basal_amt'] is None or prev['basal_amt'] is None:
            raise Exception('NULL value got through')
        if (row['date_time'] - prev['date_time']) > time_delay:
            gaps.append(prev)
            num_gaps += 1
            if not update:
                print '{} | {} {} | {} - {} = {}'.format(
                    ('%3s' % num_gaps),
                    ('%8d' % prev['rec_num']),
                    ('%8d' % row['rec_num']),
                    row['date_time'], prev['date_time'],
                    row['date_time'] - prev['date_time'])
            else:
                curs2.execute('UPDATE insulin_carb_2 SET basal_gap = 1 WHERE rec_num = %s',[prev['rec_num']])
        prev = row
    return gaps

def usage():
    print '''usage: {} report|update timedelta
example: {} report 24
report finds gaps where there are no basal change for N hours, default 24
update modifies the insulin_carb_2 table to mark the gaps'''.format(sys.argv[0],sys.argv[0])

if __name__ == '__main__':
    if len(sys.argv) < 2:
        usage()
    else:
        opt = sys.argv[1]
        delay = int(sys.argv[2]) if len(sys.argv) > 2 else 24
        if opt == 'report':
            no_basal_changes(timedelta(hours=delay),update=False)
        elif opt == 'update':
            no_basal_changes(timedelta(hours=delay),update=True)
        else:
            usage()
            
        
        
