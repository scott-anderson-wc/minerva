'''Compute insulion on board (IOB) from insulin inputs and the insulin action curve.

'''

from copy import copy
import MySQLdb
import dbconn2
import csv
from collections import deque
from datetime import datetime, timedelta

CSVfilename = 'insulin_action_curves.csv'
CSVcolumn = 4          # index into the row; empirically, this is zero-based
EPOCH_FORMAT = '%Y-%m-%d %H:%M:%S'
US_FORMAT = '%m/%d %H:%M'

def get_dsn():
    return dbconn2.read_cnf()

def get_conn(dsn=get_dsn()):
    return dbconn2.connect(dsn)

def csv_values():
    with open(CSVfilename, 'rU') as csvfile:
        reader = csv.reader(csvfile) # default format is Excel
        return [ row for row in reader ]

def read_insulin_action_curve():
    '''Return the insulin action curve as an array, projecting just one
    column of the Excel spreadsheet (as a CSV file)'''
    with open(CSVfilename, 'rU') as csvfile:
        reader = csv.reader(csvfile) # default format is Excel
        vals = [ row[CSVcolumn] for row in reader ]
        # skip first row, which is the header
        return vals[1:]

def first_insulin_rows(conn=get_conn(), N=60):
    curs = conn.cursor(MySQLdb.cursors.DictCursor) # results as Dictionaries
    curs.execute('SELECT Basal_amt,bolus_volume FROM insulin_carb LIMIT %s',
                 [N])
    return curs.fetchall()

def gen_rows(conn=get_conn()):
    curs = conn.cursor(MySQLdb.cursors.DictCursor) # results as Dictionaries
    curs.execute('SELECT epoch,Basal_amt,bolus_volume FROM insulin_carb')
    while True:
        row = curs.fetchone()
        if row is None:
            return
        yield row
        
def float_or_none(x):
    return float(x) if type(x) == type(u'') and len(x) > 0 else None

def gen_rows_coerced(conn=get_conn(),rows=None):
    '''generate rows with datatypes coerced'''
    if rows is None:
        rows = gen_rows(conn)
    for row in rows:
        # row['epoch'] = datetime.strptime(row['epoch'],EPOCH_FORMAT)
        row['Basal_amt'] = float_or_none(row['Basal_amt'])
        row['bolus_volume'] = float_or_none(row['bolus_volume'])
        yield row

def time_rounded(date_in):
    '''Returns a new datetime object (datetimes are immutable) with the
    minutes rounded to the nearest five minute mark'''
    def roundn(x,n):
        return int(round(float(x)/float(n))*float(n))
    
    d = date_in
    m = roundn(d.minute,5.0)
    if m == 60:
        # by subtracting 5 minutes and then adding a timedelta, it handles
        # all the rollover of hours, days, even months. (Think about an
        # entry at 12/31 23:59.)
        date_mod = datetime(d.year,d.month,d.day,d.hour,m-5,d.second)
        date_mod = date_mod+timedelta(minutes=5)
    else:
        date_mod = datetime(d.year,d.month,d.day,d.hour,m,d.second)
    return date_mod

def compute_rtime(row):
    rtime = time_rounded(row['epoch'])
    row['rtime'] = rtime
    return rtime

merged_rows = []

def merge_rows(row1, row2):
    # there are only three keys, and we only get here if epoch values are equal, so
    # we only have to worry about Basal_amt and Bolus_volume. Actually, it seems
    # like we just have to use the second row, since everything is overriding
    print('Merging rows! at time'+row1['epoch'].strftime(US_FORMAT))
    merged_rows.append([row1,row2])

def gen_all_rows(conn=get_conn(),rows=None):
    '''This version generates virtual rows, with timestamps at 5 minute intervals'''
    if rows is None:
        rows = gen_rows_coerced(conn)
    curr_row = rows.next()
    next_row = rows.next()
    curr_time = compute_rtime(curr_row)
    next_time = compute_rtime(next_row)
    delta5 = timedelta(minutes=5)
    global merged_rows
    merged_rows = []
    while True:
        if next_time == curr_time:
            merge_rows(curr_row,next_row)
        if next_time - curr_time < delta5:
            # advance everything. if there's no next row, this will raise
            # StopIteration, which is perfect
            curr_row = next_row
            next_row = rows.next()
            curr_time = compute_rtime(curr_row)
            next_time = compute_rtime(next_row)
        # make a virtual row
        vrow = copy(curr_row)
        vrow['rtime'] = curr_time
        curr_time = curr_time + delta5
        yield vrow

def gen_all_rows_basals(conn=get_conn(),rows=None):
    '''This version generates virtual rows, with timestamps at 5 minute
    intervals and the basals divided by 12 and trickled into every
    row. Added under a new key, 'basal_drip'.'''
    if rows is None:
        rows = gen_all_rows(conn)
    curr_basal = None
    for row in rows:
        row_basal = row['Basal_amt']
        if row_basal is None and curr_basal is None:
            # still waiting for first real value
            continue
        if curr_basal is None:
            # first real value
            curr_basal = row_basal / 12.0
        if row_basal is not None:
            curr_basal = row_basal / 12.0
        row['basal_drip'] = curr_basal
        print row
        yield row

def prefix(iterable,n=10):
    return [ iterable.next() for i in range(n) ]

def print_rows(rows):
    def kv_to_str(k,v):
        if type(v) == datetime:
            v = v.strftime(US_FORMAT)
        return "{key}: {val}".format(key=k,val=v)

    for r in rows:
        print(', '.join([ kv_to_str(k,v) for k,v in r.items() ]))

def count(iterator):
    n = 0
    for item in iterator:
        n += 1
    return n

def all_rows(conn):
    def f(row):
        row['timestamp'] = datetime.strptime(row['epoch'],EPOCH_FORMAT)
        return row
    return [ f(row) for row in gen_rows(conn) ]

    

def compute_insulin_on_board(conn,n=60):
    '''read rows from insulin_carb table convolve the insulin values with
    insulin_action_curve (IAC) to get insulin_on_board (IOB), writing the
    latter out to a new table.

    Strategy: preload N rows of IAC. Hold N rows of insulin_carb in
    memory. Have N running sums going simultaneously. On each iteration,
    update the running sums. Write out the oldest one to the new table,
    since it's now done. Discard the oldest insulin_carb, since it's no
    longer needed. Shift the running sums and the insulin_carb
    arrays. Load a new row from insulin_carb and initialize the new
    running sum. Repeat.

    Instead of using arrays, I'll use deques for holding the rows and the
    sums. No, cancel that; they're slow, O(n) for indexed access to the
    middle, and we'll be iterating over them every time.  So, I'll build
    my own.

    Actually, let's use deques for now (zero debugging) and switch to
    home-grown only if performance is an issue. Since this is an offline
    algorithm (we're pre-computing IOB), performance doesn't matter.
    '''
    sums = deque( [ 0 for i in range(N) ], N)
    ic_rows = deque( first_insulin_rows(conn,N), N)

    
def main():
    dsn = dbconn2.read_cnf()
    dbconn2.connect(dsn)
    compute_insulin_on_board(conn)
    
def test():
    global N, iac, first60
    iac = read_insulin_action_curve()
    print('insulin_action_curve',iac)
    N = len(iac)
    dsn = dbconn2.read_cnf()
    conn = dbconn2.connect(dsn)
    first60 = first_insulin_rows(conn,len(iac))
    print('first {n}'.format(n=N))
    print_rows(first60)
    print('done!')
    return {'N':N,'iac':iac,'first60':first60}

def test():
    global grows
    grows = prefix(gen_all_rows_basals(),100)
    print_rows(grows)


if __name__ == '__main__':
    test()
