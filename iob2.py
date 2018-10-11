#!/usr/bin/env python

'''Compute insulion on board (IOB) from insulin inputs and the insulin action curve.

This is the version running on hughnew. It uses different table names
versus the one on tempest, specifically insulin_carb_2 rather than insulin_carb.

'''

from copy import copy
import MySQLdb
import dbconn2
import csv
import itertools
from collections import deque
from datetime import datetime, timedelta
import decimal                  # some MySQL types are returned as type decimal
import pandb

SERVER = 'hughnew'              # hughnew versus tempest
# CSVfilename = 'insulin_action_curves.csv'
CSVfilename = 'insulin_action_curves-chart-smoothed.csv'
CSVcolumn = 4          # index into the row; empirically, this is zero-based
EPOCH_FORMAT = '%Y-%m-%d %H:%M:%S'
RTIME_FORMAT = '%Y-%m-%d %H:%M'
US_FORMAT = '%m/%d %H:%M'
CSV_FORMAT = '%Y-%m-%d %H:%M'
REAL_KEYS = ['epoch','bolus_volume','Basal_amt','carbs']
ICS_KEYS = ['rtime','basal_amt_12','bolus_volume','basal_amt','carbs','real_row','rec_num']
IOB_KEYS = ICS_KEYS[:]
IOB_KEYS.extend(['active_insulin','rescue_carbs','corrective_insulin','tags'])

def get_dsn():
    return dbconn2.read_cnf()

def get_conn(dsn=get_dsn()):
    return dbconn2.connect(dsn)

def csv_values():
    with open(CSVfilename, 'rU') as csvfile:
        reader = csv.reader(csvfile) # default format is Excel
        return [ row for row in reader ]

def csv_generator(csvfilename):
    '''returns an iterator that yields rows from the given CSV file as tuples'''
    with open(csvfilename, 'rU') as csvfile:
        reader = csv.reader(csvfile) # default format is Excel
        for row in reader:
            yield row

def csv_dict_generator(csvfilename):
    '''returns an iterator that yields rows from the given CSV file as dictionaries'''
    with open(csvfilename, 'rU') as csvfile:
        reader = csv.reader(csvfile) # default format is Excel
        header = reader.next()
        for row in reader:
            yield dict(zip(header,row))

key_defaults = {'user': None,
                'Basal_amt': 0.0,
                'basal_amt_12': 0.0,
                'bolus_volume': 0.0,
                'carbs': 0.0,
                'notes': None,
                'real_row': 0,
                'rec_num': None,
                'rescue_carbs': 0,
                'corrective_insulin': 0,
                'mgdl': 0,      # will be overwritten with data from cgm_2
                'tags': ''}

def format_elt(elt,key):
    if elt is None:
        return key_defaults[key]
    elif type(elt) == datetime:
        return elt.strftime(CSV_FORMAT)
    elif type(elt) == float:
        return elt
    elif type(elt) == int:
        return elt
    elif type(elt) == long:
        return elt
    elif type(elt) == decimal.Decimal:
        return float(elt)
    elif type(elt) == bool:
        return 1 if elt else 0
    elif type(elt) == str or type(elt) == unicode:
        return elt
    else:
        raise TypeError('no format for type {t} with value {v}'.format(t=type(elt), v=elt))

def listify_row(row,keys=ICS_KEYS):
    '''Returns a list suitable for output to a CSV file. Keys are listed in the order of the given arg'''
    return [ format_elt(row[key],key) if key in row else '' for key in keys ]

def csv_output(rows, CSVfilename, keys):
    '''Write the rows (can be an iterable) to the given filename'''
    with open(CSVfilename, 'wb') as csvfile:
        writer = csv.writer(csvfile) # default format is Excel
        writer.writerow(keys)
        for row in rows:
            writer.writerow(listify_row(row,keys))

def csv_output_all(rows, CSVfilename):
    '''Write the rows (can be an iterable) to the given filename; first line of output is all the keys in the first row.'''
    with open(CSVfilename, 'wb') as csvfile:
        writer = csv.writer(csvfile) # default format is Excel
        row1 = rows.next()
        writer.writerow(row1.keys())
        for row in itertools.chain([row1],rows):
            writer.writerow(listify_row(row,keys))

def integers():
    n = 0
    while True:
        n += 1
        yield n

def prefix(iterable,n=10):
    i = 0
    while i < n:
        i += 1
        yield iterable.next()

def prefix_list(iterable,n=10):
    return list(prefix(iterable,n))

def print_rows(rows):
    '''Print a sequence of rows. Rows can be an iterable, like gen_insulin_carb_vrows()'''
    def kv_to_str(k,v):
        if type(v) == datetime:
            v = v.strftime(US_FORMAT)
        return "{key}: {val}".format(key=k,val=v)

    for (i,r) in enumerate(rows):
        print(str(i)+': '+', '.join([ kv_to_str(k,v) for k,v in r.items() ]))

def count(iterator):
    n = 0
    for item in iterator:
        n += 1
    return n

def printIt(iterator,limit=None):
    '''Print every element of an iterator. For long or infinite iterators, use a numerical limit'''
    i = 0
    for elt in iterator:
        i += 1
        if limit is not None and i >= limit:
            return
        print i, elt

def float_or_none(x):
    if (type(x) == unicode or type(x) == str) and len(x) > 0:
        return float(x)
    elif x == '' or x == u'':
        return None
    elif type(x) == decimal.Decimal:
        return float(x)
    elif x is None:
        return None
    else:
        raise TypeError("Don't know how to coerce {x} of type {t}".format(x=x,t=type(x)))

    return float(x) if (type(x) == unicode or type(x) == str) and len(x) > 0 else None

def float_or_zero(x):
    if (type(x) == unicode or type(x) == str) and len(x) > 0:
        return float(x)
    elif type(x) == float:
        return x
    elif type(x) == decimal.Decimal:
        return float(x)
    elif x is None:
        return 0.0
    else:
        raise TypeError("Don't know how to coerce {x} of type {t}".format(x=x,t=type(x)))

def time_rounded(date_in):
    '''Returns a new datetime object (datetimes are immutable) with the
    minutes rounded to the nearest five minute mark'''
    def roundn(x,n):
        return int(round(float(x)/float(n))*float(n))
    
    d = date_in
    assert(type(d)==datetime)
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

# ================================================================
# Pipeline code        

'''
# not used
def all_rows(conn):
    def f(row):
        row['timestamp'] = datetime.strptime(row['epoch'],EPOCH_FORMAT)
        return row
    return [ f(row) for row in gen_rows(conn) ]
'''

def gen_rows(conn=get_conn(),pipeIn=None,year=None,month=None,day=None):
    if pipeIn is None:
        curs = conn.cursor(MySQLdb.cursors.DictCursor) # results as Dictionaries
        if SERVER == 'hughnew':
            select = 'SELECT date_time as epoch,Basal_amt,bolus_volume,carbs,rec_num FROM insulin_carb_2'
        else:
            select = 'SELECT epoch,Basal_amt,bolus_volume,rec_num FROM insulin_carb'
        if year is not None and month is not None and day is not None:
            select += ' WHERE year(date_time) = {year} and month(date_time) = {month} and day(date_time)={day}'.format(year=year, month=month, day=day)
        elif year is not None:
            select += ' WHERE year(date_time) = {year}'.format(year=year)
        curs.execute(select)
        while True:
            row = curs.fetchone()
            if row is None:
                return
            yield row
    else:
        # substitute source
        for row in pipeIn:
            yield row
        
cursor_columns = None

def row_get(row,key):
    if cursor_columns is None:
        raise 'Forgot to set cursor columns!'
    return row[cursor_columns.index(key)]

def row_set(row,key,val):
    if cursor_columns is None:
        raise 'Forgot to set cursor columns!'
    row[cursor_columns.index(key)] = val
    return row

def gen_rows_ics(conn=get_conn(),year=None):
    curs = conn.cursor()
    select = 'SELECT * FROM insulin_carb_smoothed'
    if year is not None:
        select += ' WHERE year(date_time) = {year}'.format(year=year)
    curs.execute(select)
    global cursor_columns
    cursor_columns = [ desc[0] for desc in curs.description ]
    while True:
        row = curs.fetchone()
        if row is None:
            return
        yield list(row)         # conses a lot, but ...

def coerce_row(row):
    '''coerce the datatypes in the row'''
    # data from database is already a datetime, but test data might not be
    if type(row['epoch']) == str:
        row['epoch'] = datetime.strptime(row['epoch'],EPOCH_FORMAT)
    row['Basal_amt'] = float_or_none(row['Basal_amt'])
    row['bolus_volume'] = float_or_none(row['bolus_volume'])
    return row

def coerce_smoothed_row(row):
    '''coerce the datatypes in the smoothed row'''
    # data from database is already a datetime, but test data might not be
    if type(row['rtime']) == str:
        row['rtime'] = datetime.strptime(row['rtime'],RTIME_FORMAT)
    row['basal_amt_12'] = float_or_zero(row['basal_amt_12'])
    row['bolus_volume'] = float_or_zero(row['bolus_volume'])
    return row

def gen_rows_coerced(conn=get_conn(),rows=None,pipeIn=None):
    '''generate rows with datatypes coerced, reading from rows'''
    if rows is None:
        rows = gen_rows(conn,pipeIn=pipeIn)
    for row in rows:
        yield coerce_row(row)

merged_rows = []                # global for debugging

def merge_rows(src, dest):
    '''puts any values from row2 into row1'''
    # there are only three keys, and we only get here if epoch values
    # are equal, so we only have to worry about Basal_amt,
    # Bolus_volume and carbs. Because of the carbs, we can't just use
    # the second row; otherwise we could because the later basal
    # values would override the earlier values. If there were two
    # boluses, we'd probably want to sum them.
    if False:
        merged_rows.append( (src,dest) )
    def combine(src,dest,key):
        if src[key] is None:
            return
        if dest[key] is None:
            dest[key] = src[key]
        else:
            s = src[key]
            d = dest[key]
            ts = type(s)
            td = type(d)
            # TODO: use float for every numerical type
            if ((ts == int or ts == float or ts == decimal.Decimal) and
                (td == int or td == float or td == decimal.Decimal)):
                if s == d:
                    #merged_rows.append('merged rows have same value for {key}; using that'
                    #                   .format(key=key))
                    merged_rows.append( (key, s) )
                else:
                    dest[key] = s+d
            else:
                raise TypeError('cannot merge {key} for src {s} and dst {d}'.
                                format(key=key,s=s,d=d))
    combine(src,dest,'bolus_volume')
    combine(src,dest,'Basal_amt')
    combine(src,dest,'carbs')
    return dest

def gen_insulin_carb_vrows(conn=get_conn(),rows=None, pipeIn=None):
    '''This version generates virtual rows from rows (real ones), with
    timestamps at 5 minute intervals. It's the basis of the
    insulin_carb_smoothed table.'''
    if rows is None:
        rows = gen_rows_coerced(conn=conn,pipeIn=pipeIn)
    # Loop over real rows, creating virtual rows. The invariant is that
    # curr <= vrow < next. When vrow catches up to next, discard curr,
    # make curr be next, and get another next. If timestamp of new next is
    # equal to curr, merge them and get another next.
    curr_row = rows.next()
    next_row = rows.next()
    curr_time = compute_rtime(curr_row)
    next_time = compute_rtime(next_row)
    if curr_time == next_time:
        raise Exception('before loop: next row time equals curr row time')
    vrow_time = curr_time
    delta5 = timedelta(minutes=5)
    global merged_rows
    debug = False
    merged_rows = []
    # print('vrow_time',vrow_time,'next_time',next_time)
    try:
        while True:
            # This outer loop produces vrows
            # print('vrow_time',vrow_time,'next_time',next_time)
            if vrow_time >= next_time:
                # this inner loop pulls in real rows
                # advance everything. if there's no next row, this will raise
                # StopIteration, which is perfect
                while True:
                    curr_row = next_row
                    curr_time = next_time
                    next_row = rows.next()
                    next_time = compute_rtime(next_row)
                    if debug:
                        print('advance to ({ct} {ctr} and {nt} {ntr}) {diff}'
                              .format(ct=curr_time,nt=next_time,
                                      ctr=curr_row['rec_num'],
                                      ntr=next_row['rec_num'],
                                      diff='greater' if next_time > curr_time else 'merge!'))
                    if next_time > curr_time:
                        break
                    # merge from curr into next, since the top of the
                    # loop discards curr_row
                    merge_rows(curr_row, next_row)
            # make a virtual row. We will selectively copy from real row later
            vrow = {'rtime': vrow_time, 'real_row': vrow_time == curr_time}
            # copy from real row
            if debug:
                # print('vrow_time',vrow_time,'curr_time',curr_time)
                if vrow_time == curr_time:
                    print 'match! copy from ',curr_row
            for key in ['carbs', 'Basal_amt', 'bolus_volume','rec_num']:
                if vrow_time == curr_time:
                    # print 'real row, key {k} is {v}'.format(k=key,v=curr_row[key])
                    if key in curr_row:
                        vrow[key] = curr_row[key]
                    else:
                        vrow[key] = None
                else:
                    vrow[key] = None
            vrow_time = vrow_time + delta5
            yield vrow
    except StopIteration:
        print '''Done generating virtual rows. End time is {end}
and end rec_num is {r} and we merged {nmerge} rows'''.format(end=curr_row['rtime'],
                                                             r=curr_row['rec_num'],
                                      nmerge=len(merged_rows))

def gen_all_rows_basals(conn=get_conn(),rows=None,pipeIn=None):
    '''This version generates virtual rows, with timestamps at 5 minute
    intervals and the basals divided by 12 and trickled into every
    row. Added under a new key, 'basal_amt_12'. The input is expected to
    be complete, where every row has a Basal_amt'''
    if rows is None:
        rows = gen_insulin_carb_vrows(conn=conn,pipeIn=pipeIn)
    curr_basal = None
    for row in rows:
        row_basal = row['Basal_amt']
        if row_basal is None:
            if curr_basal is None:
                # keep waiting for first real value
                continue
            else:
                # we use the prior real value, skipping this "None"
                pass
        else:
            # change the current value based on this new setting
            curr_basal = row_basal / 12.0
        row['basal_amt_12'] = curr_basal
        yield row

# ================================================================
# Insulin Action code

def read_insulin_action_curve(col=CSVcolumn,test=True):
    '''Return the insulin action curve as an array, projecting just one
    column of the Excel spreadsheet (as a CSV file). The CSVcolumn is an
    index into the row, and the default value, 6, is the scaled Bernstein
    curve.'''
    if test:
        print 'USING TEST IAC'
        return [ 0, 0.5, 1.0, 0.75, 0.5, 0.25, 0 ]
    else:
        print 'USING REAL IAC'
        with open(CSVfilename, 'rU') as csvfile:
            reader = csv.reader(csvfile) # default format is Excel
            headers = reader.next()
            print('CSV headers are '+str(headers))
            print('Using column {n} labeled {x}'.format(n=col,x=headers[col]))
            vals = [ row[col] for row in reader ]
            # skip first row, which is the header
            return [ float(x) for x in vals]

'''
def first_insulin_rows(conn=get_conn(), N=60):
    curs = conn.cursor(MySQLdb.cursors.DictCursor) # results as Dictionaries
    curs.execute('SELECT Basal_amt,bolus_volume FROM insulin_carb LIMIT %s',
                 [N])
    return curs.fetchall()
'''

def read_insulin_carb_smoothed(csvfile='insulin_carb_smoothed.csv',test=True):
    if test:
        csvfile = 'insulin_carb_smoothed_test1.csv'
    return csv_dict_generator(csvfile)

def compute_insulin_on_board(rows=None,test_data=True,showCalc=True,test_iac=True):
    '''read rows from insulin_carb table convolve the insulin values with
    insulin_action_curve (IAC) to get active_insulin (AI), writing the
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

    I don't want to learn deques right now. I want to use an array of N
    rows, representing the last N 5' intervals. Then, the basic alg is

    loop:
        read a new row.
        Initialize its iob to zero.
        put it on the beginning of the N rows
        increase every row's IOB total by the product of IA[i] and Ins[i]
        write out the end of the N rows and remove it
    '''
    IAC = read_insulin_action_curve(test=test_iac)
    N = len(IAC)
    lastrows = []
    if rows is None:
        rows = read_insulin_carb_smoothed(test=test_data)
    print('showCalc is {sc}'.format(sc=showCalc))
    for row in rows:
        # print('row1',row)
        row['active_insulin'] = 0.0
        # because we're adding rows onto the front, that has the effect of time-reversing
        # the IAC
        lastrows.insert(0, row)
        if showCalc:
            calc = []
            row['active_insulin_calc'] = 'not yet'
        # if len(lastrows) < N:
        #    continue
        # ================================================================
        # the previous lines are for all rows, including the first N-1 rows
        incr = 0
        for i in xrange(min(N,len(lastrows))):
            prevrow = lastrows[i]
            ins_act = IAC[i]
            if showCalc:
                calc.append((ins_act,prevrow['basal_amt_12']+prevrow['bolus_volume']))
            incr += ins_act*(prevrow['basal_amt_12']+prevrow['bolus_volume'])
        # might be zero, but so what
        newest = lastrows[0]
        newest['active_insulin'] = incr
        if showCalc:
            newest['active_insulin_calc'] = str(calc)
        # print('number of buffered rows: {n}'.format(n=len(lastrows)))
        if len(lastrows) > N:
            yield lastrows.pop()
    # After loop over all input rows, produce all the lastrows
    for last in lastrows:
        yield last
    
def compute_active_insulin(rows=None,test_data=False,showCalc=False,test_iac=False):
    '''read rows from insulin_carb table convolve the insulin values with
    insulin_action_curve (IAC) to get active_insulin (AI), now called
    dynamic_insulin. Yields the data as a generator.
    '''
    # should update this to the shiftdown() technique; saves a lot of consing
    IAC = read_insulin_action_curve(test=test_iac)
    N = len(IAC)
    lastrows = []
    if rows is None:
        rows = read_insulin_carb_smoothed(test=test_data)
    print('showCalc is {sc}'.format(sc=showCalc))
    for row in rows:
        # print('row1',row)
        row_set(row,'active_insulin', 0.0)
        # because we're adding rows onto the front, that has the effect of time-reversing
        # the IAC
        lastrows.insert(0, row)
        # ================================================================
        # the previous lines are for all rows, including the first N-1 rows
        incr = 0
        for i in xrange(min(N,len(lastrows))):
            prevrow = lastrows[i]
            ins_act = IAC[i]
            ins_in = (row_get(prevrow,'basal_amt_12') +
                      row_get(prevrow,'bolus_volume'))
            if showCalc:
                calc.append((ins_act,ins_in))
            incr += ins_act*ins_in
        # might be zero, but so what
        newest = lastrows[0]
        row_set(newest,'active_insulin', incr)
        if showCalc:
            row_set(newest,'active_insulin_calc', str(calc))
        # print('number of buffered rows: {n}'.format(n=len(lastrows)))
        if len(lastrows) > N:
            yield lastrows.pop()
    # After loop over all input rows, produce all the lastrows
    for last in lastrows:
        yield last
    
def main():
    dsn = dbconn2.read_cnf()
    dbconn2.connect(dsn)
    compute_insulin_on_board(conn)
    
'''
def test_iob():
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
'''

def run_iob(test_data=True, showCalc=True, test_iac=True):
    if test_data:
        rows = gen_all_rows_basals( pipeIn=ic_test_data1() )
        outfile = 'iob_on_test_data.csv'
    else:
        rows = gen_all_rows_basals( pipeIn=None )
        outfile = 'iob_on_real_data.csv'
    iob_rows = compute_insulin_on_board(rows=rows, test_data=test_data, test_iac=test_iac, showCalc=showCalc)
    if showCalc:
        keys = IOB_KEYS[:]
        keys.append('iob_calc')
    else:
        keys = IOB_KEYS
    rows = list(iob_rows)
    csv_output(rows, outfile, keys)

    
# ================================================================
# Find rescue carb events, defined as carbs w/o insulin in +/- 30 minutes.
# Also find corrective insulin, defined as insulin w/o carbs in +/- 30 minutes.
# So, we'll combine those since they use a similar window.    

def find_rescue_events(rows=None):
    '''Get a 65 minute window of data, checking the middle of it for
    rescue events. Put rescue events in two new columns, and add elements
    to a 'tags' column. '''
    window = []
    winsize = 65/5                 # number of rows in the window

    def addCol(row,key,init):
        if key not in row:
            row_set(row,key,init)

    def initRow(row):
        addCol(row,'tags','')
        addCol(row,'rescue_carbs',0)
        addCol(row,'corrective_insulin',0)
        return row

    while len(window) < winsize:
        window.append(initRow(rows.next()))
    middle = int(winsize/2)
    after = row_get(window[winsize-1],'rtime')
    before = row_get(window[0],'rtime')
    print('window temporal size is {after} - {before} = {diff}'.format(after=after,
                                                                       before=before,
                                                                       diff=(after-before)))
    def anyCarbs(seq):
        for s in seq:
            if row_get(s,'carbs') > 0:
                return True
        return False

    def anyInsulin(seq):
        for s in seq:
            if row_get(s,'bolus_volume') > 0:
                return True
        return False

    def addTag(row,tag):
        curr = row_get(row,'tags')
        new = (curr + ' ' + tag) if curr != '' else tag
        row_set(row,'tags',new)

    rescue_carb_events = 0
    corrective_insulin_events = 0

    try:
        while True:
            mid = window[middle]
            if row_get(mid,'carbs') > 0 and not anyInsulin(window):
                # print('FOUND RESCUE CARBS! at ',mid['rtime'])
                rescue_carb_events += 1
                addTag(mid,'rescue_carbs')
                row_set(mid,'rescue_carbs', 1)
            if row_get(mid,'bolus_volume') > 0 and not anyCarbs(window):
                corrective_insulin_events += 1
                # print('FOUND RESCUE INSULIN! at ',mid['rtime'])
                addTag(mid,'corrective_insulin')
                row_set(mid,'corrective_insulin', 1)
            out = window[0]
            pipe.shift(window,initRow(rows.next()))
            yield out
    except StopIteration:
        print 'found {x} rescue_carb events and {y} corrective_insulin_events'.format(
            x=rescue_carb_events,
            y=corrective_insulin_events)
        for r in window:
            yield r

def meal_name(mealtime):
    '''Return the meal name:

    breakfast: 6-11
    lunch: 11-15
    snack: 15-17:30
    dinner: 17:30-21:00

'''
    mins = mealtime.hour*60+mealtime.minute
    if mins < 6*60:
        return 'before6'
    elif mins < 11*60:
        return 'breakfast'
    elif mins < 15*60:
        return 'lunch'
    elif mins < 17*60+30:
        return 'snack'
    elif mins < 21*60:
        return 'dinner'
    else:
        return 'after9'

def categorize_carbs(rows=None):
    '''Get a 65 minute window of data, checking the middle of it for
    rescue events. Any carbs with insulin are a meal. Put categories
    in the 'tags' column.
    '''
    window = []
    winsize = 65/5                 # number of rows in the window

    def addCol(row,key,init):
        if key not in row:
            row_set(row,key,init)

    def initRow(row):
        addCol(row,'tags','')
        addCol(row,'rescue_carbs',0)
        addCol(row,'corrective_insulin',0)
        return row

    while len(window) < winsize:
        window.append(initRow(rows.next()))
    middle = int(winsize/2)
    after = row_get(window[winsize-1],'rtime')
    before = row_get(window[0],'rtime')
    print('window temporal size is {after} - {before} = {diff}'.format(after=after,
                                                                       before=before,
                                                                       diff=(after-before)))
    def anyCarbs(seq):
        for s in seq:
            if row_get(s,'carbs') > 0:
                return True
        return False

    def anyInsulin(seq):
        for s in seq:
            if row_get(s,'bolus_volume') > 0:
                return True
        return False

    def addTag(row,tag):
        curr = row_get(row,'tags')
        new = (curr + ' ' + tag) if curr != '' else tag
        row_set(row,'tags',new)

    rescue_carb_events = 0
    corrective_insulin_events = 0
    mealcounts = {'before6': 0,
                  'breakfast': 0,
                  'lunch': 0,
                  'snack': 0,
                  'dinner': 0,
                  'after9': 0}

    try:
        while True:
            mid = window[middle]
            # carbs are complicated
            if row_get(mid,'carbs') > 0:
                if anyInsulin(window):
                    name = meal_name(row_get(mid,'rtime'))
                    mealcounts[name] += 1
                    if name == 'before6' or name == 'after9':
                        print name
                    addTag(mid,name)
                else:
                    # print('FOUND RESCUE CARBS! at ',mid['rtime'])
                    rescue_carb_events += 1
                    addTag(mid,'rescue_carbs')
                    row_set(mid,'rescue_carbs', 1)
            # corrective insulin
            if row_get(mid,'bolus_volume') > 0 and not anyCarbs(window):
                corrective_insulin_events += 1
                # print('FOUND RESCUE INSULIN! at ',mid['rtime'])
                addTag(mid,'corrective_insulin')
                row_set(mid,'corrective_insulin', 1)
            out = window[0]
            pipe.shift(window,initRow(rows.next()))
            yield out
    except StopIteration:
        print 'found {x} rescue_carb events and {y} corrective_insulin_events'.format(
            x=rescue_carb_events,
            y=corrective_insulin_events)
        print 'meal counts',mealcounts
        for r in window:
            yield r

# ================================================================
# Output to database tables

def db_output(rows, tablename, keys):
    '''Write rows (can be an iterable) to the given table'''
    conn = get_conn()
    curs = conn.cursor(MySQLdb.cursors.DictCursor) # results as Dictionaries
    # clear out old data
    curs.execute('delete from {table}'.format(table=tablename))
    sql = 'insert into {table}({cols}) values({vals})'.format(
        table=tablename,
        cols=','.join(keys),
        vals=','.join(['%s' for k in keys]))
    print('insert using ',sql)
    insert_count = 0
    for row in rows:
        # wow, this is a lot of consing; hopefully GC can keep up
        if len(row.keys()) != len(keys):
            for k in keys:
                if k not in row:
                    raise Exception('row is missing some keys, including',k)
        insert_count += 1
        if insert_count % 1000 == 0:
            print str(insert_count)+' '
        curs.execute(sql,listify_row(row,keys))


def db_update(rows, tablename, keys):
    '''Update rows (can be an iterable) to the given table'''
    conn = get_conn()
    curs = conn.cursor()
    curs.execute('select * from {table}'.format(table=tablename))
    global cursor_columns
    cursor_columns = [ desc[0] for desc in curs.description ]
    settings = ','.join( [ '{col} = %s'.format(col=key) for key in cursor_columns ] )
    curs = conn.cursor()
    sql = 'update {table} set {settings} where rec_num = %s'.format(
        table=tablename,
        settings = settings)
    print('update using ',sql)
    insert_count = 0
    for row in rows:
        if len(row) != len(cursor_columns):
            raise Exception('row has wrong length')
        insert_count += 1
        if insert_count % 1000 == 0:
            print str(insert_count)+' '
        data = list(row)
        data.append(row_get(row,'rec_num')) # extra occurrence for the key
        curs.execute(sql,data)


# ================================================================
# Testing code for insulin_carb_smoothed

def run_ics(test=True):
    if test:
        pipeIn = ic_test_data1()
        outfile = 'insulin_carb_test_data_smoothed.csv'
    else:
        pipeIn = None
        outfile = 'insulin_carb_real_data_smoothed.csv'
    rows = gen_all_rows_basals( rows=None,
                                pipeIn=pipeIn)
    csv_output(rows, outfile, ICS_KEYS)
    
def ic_test_data1():
    '''Test data for smoothing. An initial bolus with no basal, then a basal, and then both'''
    for row in [
        {'epoch': '2016-08-08 07:00:00', 'Basal_amt': u'0.0', 'bolus_volume': u'0.0'}, # start at zero
        {'epoch': '2016-08-08 08:00:00', 'Basal_amt': u'0.0', 'bolus_volume': u'2.0'}, # bolus
        {'epoch': '2016-08-08 09:00:00', 'Basal_amt': u'2.4', 'bolus_volume': u'0.0'}, # basal at 0.2 per 5' interval
        {'epoch': '2016-08-08 10:00:00', 'Basal_amt': u'2.4', 'bolus_volume': u'2.0'}, # both
        {'epoch': '2016-08-08 11:00:00', 'Basal_amt': u'0.0', 'bolus_volume': u'0.0'}, # neither
        {'epoch': '2016-08-08 12:00:00', 'Basal_amt': u'0.0', 'bolus_volume': u'0.0'}, # last row
        ]:
        print('draw from ic_test_data1')
        yield row

def write_ic_data(test=True):
    if test:
        csv_output(ic_test_data1(), 'insulin_carb_test_data.csv', ['epoch', 'Basal_amt', 'bolus_volume'])
    else:
        csv_output(gen_rows(), 'insulin_carb_real_data.csv',  ['epoch', 'Basal_amt', 'bolus_volume'])

def write_test_stuff():
    write_ic_data(test=True)    # insulin_carb_test_data.csv
    run_ics(test=True)          # insulin_carb_test_data_smoothed.csv
    run_iob(test_data=True)     # iob_on_test_data.csv

def write_real_stuff():
    write_ic_data(test=False)    # insulin_carb_real_data.csv
    run_ics(test=False)          # insulin_carb_real_data_smoothed.csv
    run_iob(test_data=False,test_iac=False,showCalc=False) # iob_on_real_data.csv

def test1():
    # pipeIn=ic_test_data1(), outfile='insulin_carb_smoothed_test1.csv')
    run_ics(test=True)

def real1():
    run_ics(test=False)


def test2(n=20):
    global xl, yl, yln, zl, zln
    x = ic_test_data1()
    xl = list(x)
    y = gen_all_rows_basals(pipeIn=xl)
    yl = list(y)
    yln = yl[0:20]
    # print_rows(yln)
    z = compute_insulin_on_board(rows=yl)
    zl = list(z)
    zln = zl[0:n]
    print_rows(zln)
    return {'xl':xl,'yl':yl,'yln':yln,'zln':zln}


import pipe
import functools

def format_row(row):
    return '['+','.join([ str(e) for e in listify_row(row)])+']'

def format_real_row(row):
    return '['+','.join([ str(e) for e in listify_row(row,REAL_KEYS)])+']'

def print_row(row):
    print(format_row(row))

def pipe1(test=False):
    if test:
        p1 = ic_test_data1()
    else:
        p1 = gen_rows()
    # should be the same from here on
    p2 = pipe.mapiter(p1, coerce_row)
    p25 = p2 # pipe.tee(p2, prefix='real:', printer=printrow)
    p3 = gen_insulin_carb_vrows(rows = p25)
    p35 = p3 # pipe.tee(p3, prefix='vrow:', stringify=format_row)
    # pipe.more(p35, page=10, printer=printrow)
    p4 = gen_all_rows_basals(rows = p35)
    # pipe.more(p4, page=10, printer=print_row)
    return p4

def pipe2(test=False):
    '''Computes smoothed data'''
    if test:
        p1 = ic_test_data1()
    else:
        p1 = gen_rows(year=2014,month=5,day=19)
    # should be the same from here on
    p2 = pipe.mapiter(p1, coerce_row)
    p25 = pipe.tee(p2, prefix='real:', stringify=format_real_row)
    p3 = gen_insulin_carb_vrows(rows = p25)
    pipe.more(p3, page=10, printer=print_row)
    p35 = p3 # pipe.tee(p3, prefix='vrow:', printer=lambda row: print(format_row(row))
    p4 = gen_all_rows_basals(rows = p35)
    if test:
        filename = 'insulin_carb_smoothed_on_test_data.csv'
    else:
        filename = 'insulin_carb_smoothed_on_real_data.csv'
    csv_output(p4, filename, ICS_KEYS)

def pipe3(test=False):
    '''Computes active_insulin data'''
    if test:
        p1 = ic_test_data1()
    else:
        p1 = gen_rows()
    # should be the same from here on
    p2 = pipe.mapiter(p1, coerce_row)
    p25 = p2 # pipe.tee(p2, prefix='real:', printer=printrow)
    p3 = gen_insulin_carb_vrows(rows = p25)
    p35 = p3 # pipe.tee(p3, prefix='vrow:', stringify=format_row)
    # pipe.more(p35, page=10, printer=printrow)
    p4 = gen_all_rows_basals(rows = p35)
    # pipe.more(p4, page=10, printer=print_row)
    p5 = compute_insulin_on_board(rows=p4, test_data=test, test_iac=False, showCalc=False)
    if test:
        filename = 'active_insulin_on_test_data.csv'
    else:
        filename = 'active_insulin_on_real_data.csv'
    csv_output(p5, filename, IOB_KEYS)

def pipe4(test=False):
    '''Write smoothed data to .csv file'''
    print('Not yet ready for prime time')
    raise Exception
    if test:
        p1 = ic_test_data1
        filename = 'active_insulin_on_test_data.csv'
    else:
        p1 = gen_rows
        filename = 'active_insulin_on_real_data.csv'
    g = pipe.pipe( lambda x: p1(),
                   lambda x: pipe.mapiter(x, coerce_row),
                   gen_insulin_carb_vrows,
                   gen_all_rows_basals)
    csv_output(g(None), filename, IOB_KEYS)

def test_data2():
    for row in [
        {'epoch': '2016-08-08 07:00:00', 'Basal_amt': u'0.0', 'bolus_volume': u'0.0'}, # start at zero
        {'epoch': '2016-08-08 08:00:00', 'Basal_amt': u'0.0', 'bolus_volume': u'2.0'}, # rescue insulin
        {'epoch': '2016-08-08 09:00:00', 'Basal_amt': u'0.0', 'bolus_volume': u'2.0', 'carbs': 3.0}, # not rescue carbs or insulin
        {'epoch': '2016-08-08 10:00:00', 'Basal_amt': u'0.0', 'bolus_volume': u'0.0', 'carbs': 3.0}, # rescue carbs
        {'epoch': '2016-08-08 11:00:00', 'Basal_amt': u'0.0', 'bolus_volume': u'0.0'}, # last row

        ]:
        print('draw from test data')
        yield row
    

vals = None

carbs = None

def pipe_create_ics(test=False):
    '''Compute smoothed data'''
    if test:
        rows = test_data2
    else:
        rows = gen_rows
    g = pipe.pipe( lambda x: rows(),
                   lambda p: pipe.mapiter(p, coerce_row),
                   lambda p: gen_insulin_carb_vrows(rows=p), # does the actual smoothing
                   lambda p: gen_all_rows_basals(rows=p), # calc basal_amt_12
                   )
    # pipe.more(g(None))
    db_output(g(None),
              'insulin_carb_smoothed',
              ICS_KEYS)
    
def pipe_count_carbs():
    carb_count = [0]
    def count_carbs(seq):
        for s in seq:
            if s['carbs']>0:
                carb_count[0] += 1
            yield s
    g = pipe.pipe( lambda x: gen_rows(),
                   lambda p: pipe.mapiter(p, coerce_row),
                   lambda p: gen_insulin_carb_vrows(rows=p), # does the actual smoothing
                   lambda p: gen_all_rows_basals(rows=p), # calc basal_amt_12
                   count_carbs
                   )
    # pipe.more(g(None))
    pipe.exhaust(g(None),progress=1000)
    print 'carb_count',carb_count


def pipe_update_ics(test=False):
    '''Update the ICS table'''
    if test:
        raise Exception('NYI')
        rows = test_data2
    else:
        rows = gen_rows_ics
    global vals
    vals = []

    def collect(p):
        for v in p:
            vals.append(v)
            yield v

    def cat(p):
        for v in p:
            yield v

    g = pipe.pipe( lambda x: rows(),
                   compute_active_insulin,
                   find_rescue_events,
                   # lambda p: pipe.tee(p,prefix='x: ',stringify=lambda r: str(listify_row(r,IOB_KEYS))),
                   cat
                   # nonzerocarbs
                   )
    # pipe.more(g(None))
    db_update(g(None), 'insulin_carb_smoothed', IOB_KEYS)
    
def pipe_update_ics_meta(func):
    '''update the ICS table using func as filter'''
    db_update( func(gen_rows_ics()), 'insulin_carb_smoothed', IOB_KEYS)


def csv_dump(table,CSVfilename):
    conn = get_conn()
    curs = conn.cursor(MySQLdb.cursors.DictCursor) # results as Dictionaries
    curs.execute('select * from {table} limit 1'.format(table=table))
    row = curs.fetchone()
    keys = row.keys()
    curs = conn.cursor() # results as lists
    curs.execute('select * from {table}'.format(table=table))
    with open(CSVfilename, 'wb') as csvfile:
        writer = csv.writer(csvfile) # default format is Excel
        writer.writerow(keys)
        while True:
            row = curs.fetchone()
            if row is None:
                break
            writer.writerow(row)


## ================================================================
## regularizing CGM

def regularize_cgm():
    conn = get_conn()
    curs = conn.cursor()
    curs.execute('select date_time from cgm_2')
    num_conflicts = 0
    num_rounded = 0 
    while True:
        row = curs.fetchone()
        if row is None:
            break
        dt = row[0]
        reg = time_rounded(dt)
        if dt != reg:
            curs2 = conn.cursor()
            curs2.execute('select count(*) as c from cgm_2 where date_time = %s',[reg])
            c = curs.fetchone()[0]
            if c == 1:
                num_conflict += 1
                print('rounding {dt} will conflict with {reg}'.format(dt=dt,reg=reg))
            else:
                # print('rounding {dt} to {reg}'.format(dt=dt,reg=reg))
                num_rounded += 1
                curs2.execute('update cgm_2 set date_time = %s where date_time = %s',
                              [reg,dt])
    print('num rounded',num_rounded)
    print('num conflicts',num_conflicts)

## ================================================================
## Updating ics with the cgm data


if __name__ == '__main__':
    # write_real_stuff()
    # pipe5(False)
    pipe_update_ics()
