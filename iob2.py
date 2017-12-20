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

SERVER = 'hughnew'              # hughnew versus tempest
# CSVfilename = 'insulin_action_curves.csv'
CSVfilename = 'insulin_action_curves-chart-smoothed.csv'
CSVcolumn = 4          # index into the row; empirically, this is zero-based
EPOCH_FORMAT = '%Y-%m-%d %H:%M:%S'
RTIME_FORMAT = '%Y-%m-%d %H:%M'
US_FORMAT = '%m/%d %H:%M'
CSV_FORMAT = '%Y-%m-%d %H:%M'
ICS_KEYS = ['rtime','basal_amt_12','bolus_volume','Basal_amt','carbs','real_row']
IOB_KEYS = ICS_KEYS[:]
IOB_KEYS.extend(['active_insulin','rescue_carbs','rescue_insulin','tags'])

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
                'rescue_carbs': 0,
                'rescue_insulin': 0,
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

def gen_rows(conn=get_conn(),pipeIn=None):
    if pipeIn is None:
        curs = conn.cursor(MySQLdb.cursors.DictCursor) # results as Dictionaries
        if SERVER == 'hughnew':
            curs.execute('SELECT date_time as epoch,Basal_amt,bolus_volume FROM insulin_carb_2')
        else:
            curs.execute('SELECT epoch,Basal_amt,bolus_volume FROM insulin_carb')
        while True:
            row = curs.fetchone()
            if row is None:
                return
            yield row
    else:
        # substitute source
        for row in pipeIn:
            yield row
        
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
summed_boluses = []

def merge_rows(row1, row2):
    # there are only three keys, and we only get here if epoch values are
    # equal, so we only have to worry about Basal_amt and
    # Bolus_volume. Actually, it seems like we just have to use the second
    # row, since the later basal values would override the earlier
    # values. If there were two boluses, we'd probably want to sum them.
    if False:
        print('Merging rows! at time '+row1['epoch'].strftime(US_FORMAT)+' and '+row2['epoch'].strftime(US_FORMAT))
    if (row1['bolus_volume'] is not None and
        row2['bolus_volume'] is not None):
        summed_boluses.append([row1,row2])
    merged_rows.append([row1,row2])

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
    if curr_row == next_row:
        raise Exception('before loop: next row equals curr row')
    curr_time = compute_rtime(curr_row)
    next_time = compute_rtime(next_row)
    if next_time == curr_time:
        merge_rows(curr_row,next_row)
    vrow_time = curr_time
    delta5 = timedelta(minutes=5)
    global merged_rows
    merged_rows = []
    # print('vrow_time',vrow_time,'next_time',next_time)
    while True:
        # This outer loop produces vrows
        # print('vrow_time',vrow_time,'next_time',next_time)
        if vrow_time >= next_time:
            # this inner loop pulls in real rows
            # advance everything. if there's no next row, this will raise
            # StopIteration, which is perfect
            while True:
                curr_row = next_row
                next_row = rows.next()
                if curr_row == next_row:
                    raise Exception('next row equals curr row')
                curr_time = compute_rtime(curr_row)
                next_time = compute_rtime(next_row)
                '''
                print 'advance to ({rn1} {ct} and {rn2} {nt})'.format(rn1=curr_row['rec_num'],ct=curr_time,
                                                                      rn2=next_row['rec_num'],nt=next_time)
                                                                      '''
                # print 'advance to ({ct} and {nt})'.format(ct=curr_time,nt=next_time)
                if next_time == curr_time:
                    merge_rows(curr_row,next_row)
                else:
                    break
            
        # make a virtual row. We will selectively copy from real row later
        vrow = {'rtime': vrow_time, 'real_row': vrow_time == curr_time}
        # copy from real row
        for key in ['carbs', 'Basal_amt', 'bolus_volume']:
            if vrow_time == curr_time:
                if key in curr_row:
                    vrow[key] = curr_row[key]
                else:
                    vrow[key] = None
            else:
                vrow[key] = None
        vrow_time = vrow_time + delta5
        yield vrow

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
        coerce_smoothed_row(row)
        # print('row2',row)
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
# Also fine rescue insulin, defined as insulin w/o carbs in +/- 30 minutes.
# So, we'll combine those since they use a similar window.    

def find_rescue_events(rows=None):
    '''Get a 65 minute window of data, checking the middle of it for
    rescue events. Put rescue events in two new columns, and add elements
    to a 'tags' column. '''
    window = []
    winsize = 65/5                 # number of rows in the window

    def addCol(row,key,init):
        if key not in row:
            row[key] = init

    def initRow(row):
        addCol(row,'tags','')
        addCol(row,'rescue_carbs',0)
        addCol(row,'rescue_insulin',0)
        return row

    while len(window) < winsize:
        window.append(initRow(rows.next()))
    middle = int(winsize/2)
    after = window[winsize-1]['rtime']
    before = window[0]['rtime']
    print('window temporal size is {after} - {before} = {diff}'.format(after=after,
                                                                       before=before,
                                                                       diff=(after-before)))
    def anyCarbs(seq):
        for s in seq:
            if s['carbs'] > 0:
                return True
        return False

    def anyInsulin(seq):
        for s in seq:
            if s['bolus_volume'] > 0:
                return True
        return False

    def addTag(row,tag):
        if row['tags'] == '':
            row['tags'] = tag
        else:
            row['tags'] += ' '+tag

    rescue_carb_events = 0
    rescue_insulin_events = 0

    try:
        while True:
            mid = window[middle]
            if mid['carbs'] > 0 and not anyInsulin(window):
                # print('FOUND RESCUE CARBS! at ',mid['rtime'])
                rescue_carb_events += 1
                addTag(mid,'rescue_carbs')
                mid['rescue_carbs'] = 1
            if mid['bolus_volume'] > 0 and not anyCarbs(window):
                rescue_insulin_events += 1
                # print('FOUND RESCUE INSULIN! at ',mid['rtime'])
                addTag(mid,'rescue_insulin')
                mid['rescue_insulin'] = 1
            out = window[0]
            pipe.shift(window,initRow(rows.next()))
            yield out
    except StopIteration:
        print 'found {x} rescue_carb events and {y} rescue_insulin_events'.format(
            x=rescue_carb_events,
            y=rescue_insulin_events)
        for r in window:
            yield r

# ================================================================
# Output to database tables

def db_output(rows, tablename, keys):
    '''Write rows (can be an interable) to the given table'''
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
        p1 = gen_rows()
    # should be the same from here on
    p2 = pipe.mapiter(p1, coerce_row)
    p25 = p2 # pipe.tee(p2, prefix='real:', printer=printrow)
    p3 = gen_insulin_carb_vrows(rows = p25)
    p35 = p3 # pipe.tee(p3, prefix='vrow:', stringify=format_row)
    # pipe.more(p35, page=10, printer=printrow)
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

def pipe5(test=False):
    '''Compute smoothed data including rescue carbs and rescue insulin'''
    if test:
        rows = test_data2
    else:
        rows = gen_rows
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
                   lambda p: pipe.mapiter(p, coerce_row),
                   lambda p: gen_insulin_carb_vrows(rows=p), # does the actual smoothing
                   lambda p: gen_all_rows_basals(rows=p), # calc basal_amt_12
                   find_rescue_events,
                   compute_insulin_on_board,
                   # lambda p: pipe.tee(p,prefix='x: ',stringify=lambda r: str(listify_row(r,IOB_KEYS))),
                   cat
                   )
    # pipe.more(g(None))
    db_output(g(None), 'insulin_carb_smoothed', IOB_KEYS)
    

if __name__ == '__main__':
    write_real_stuff()
