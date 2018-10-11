#!/usr/bin/env python

'''Compute dynamic insulin from insulin inputs and the insulin action curve.

This is the version running on hughnew. 

Process is to process the insulin_carb_grouped (ICG) table to fill in
virtual rows (rtime values) to create the insulin_carb_smoothed table. Do that with

create_virtual_rows()

Next, we add in the bg values from mgm and cgm. That's done using a
SQL query, but we can do it via python using

join_bg_values()

Then, we need to do some processing that requires creating "windows"
where we can look at a range of rows at once.  There are several such:

1. basal_amt_12() which is 1/12 of the most recent non-null value of basal_amt, unless there is a gap
2. categorize_carbs()  Identifying meal carbs (within +/- 30 minutes of insulin) versus rescue carbs
3. compute_dynamic_insulin_and_carbs()   done using the insulin action curve and similar carb action curves
4. compute_cgm_slopes()  over 10, 30 and 45 minutes
5. compute_minutes_since()

Put these all together with

finish_insulin_carb_smoothed()

'''

import sys
import random
from copy import copy
import MySQLdb
import dbconn2
import csv
import itertools
from datetime import datetime, timedelta
import decimal                  # some MySQL types are returned as type decimal


SERVER = 'hughnew'              # hughnew versus tempest
# CSVfilename = 'insulin_action_curves.csv'
BASEDIR = '/home/hugh9/scott/devel/'
CSVfilename = BASEDIR + 'insulin_action_curves-chart-smoothed.csv'
CSVcolumn = 4          # index into the row; empirically, this is zero-based
CAC_filename = BASEDIR + 'carb_curves - csv.csv'
EPOCH_FORMAT = '%Y-%m-%d %H:%M:%S'
RTIME_FORMAT = '%Y-%m-%d %H:%M'
US_FORMAT = '%m/%d %H:%M'
CSV_FORMAT = '%Y-%m-%d %H:%M'
REAL_KEYS = ['epoch','bolus_volume','Basal_amt','carbs']
ICS_KEYS = ['rtime','basal_amt_12','bolus_volume','basal_amt','carbs','real_row','rec_num']
IOB_KEYS = ICS_KEYS[:]
IOB_KEYS.extend(['active_insulin','rescue_carbs','corrective_insulin','tags'])

IC_KEYS = None        # keys for ICG and ICS, set by keys_from_icg

DSN = None
Conn = None

def get_dsn():
    global DSN
    if DSN is None:
        DSN = dbconn2.read_cnf()
    return DSN

def get_conn(dsn=get_dsn()):
    global Conn
    if Conn is None:
        Conn = dbconn2.connect(dsn)
    return Conn

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

def keys_from_icg(conn=get_conn()):
    curs = conn.cursor()
    select = 'SELECT * FROM insulin_carb_grouped '
    curs.execute(select)
    global IC_KEYS
    IC_KEYS = [ d[0] for d in curs.description ]
    print 'IC_KEYS ',IC_KEYS

cursor_columns = None

def row_get(row,key):
    if cursor_columns is None:
        raise Exception('Forgot to set cursor columns!')
    try:
        return row[cursor_columns.index(key)]
    except ValueError:
        raise ValueError('key {} not found in cursor_columns {}'.format(key,cursor_columns))

def row_set(row,key,val):
    if cursor_columns is None:
        raise 'Forgot to set cursor columns!'
    row[cursor_columns.index(key)] = val
    return row

def gen_rows_ic_dictionaries(conn=get_conn(), start=None, end=None, tablename='insulin_carb_smoothed'):
    curs = conn.cursor(MySQLdb.cursors.DictCursor) # results as Dictionaries
    select = 'SELECT * FROM {} '.format(tablename)
    if start is not None:
        select += " WHERE rtime >= '{start}' and rtime <= '{end}' ".format(start=start,end=end)
    print 'gen_rows_ic in table {} with query {} '.format(tablename,select)
    curs.execute(select)
    global cursor_columns
    cursor_columns = [ desc[0] for desc in curs.description ]
    print 'cursor_columns: ',cursor_columns
    while True:
        row = curs.fetchone()
        if row is None:
            return
        yield row

def get_cursor_columns(conn=get_conn(),tablename='insulin_carb_smoothed'):
    curs = conn.cursor()
    curs.execute('select * from {} limit 0'.format(tablename))
    global cursor_columns
    cursor_columns = [ desc[0] for desc in curs.description ]
    return cursor_columns
    
def gen_rows_ic(conn=get_conn(),start=None, end=None, tablename='insulin_carb_smoothed'):
    curs = conn.cursor()
    select = 'SELECT * FROM {} '.format(tablename)
    if start is not None:
        select += " WHERE rtime >= '{start}' and rtime <= '{end}' ".format(start=start,end=end)
    print 'gen_rows_ic in table {} with query {} '.format(tablename,select)
    curs.execute(select)
    get_cursor_columns()        # caller may have to do this anyhow, because of the deferred execution of a generator
    global cursor_columns
    print 'cursor_columns: ',cursor_columns
    while True:
        row = curs.fetchone()
        if row is None:
            return
        yield list(row)         # conses a lot, but fetchone() returns tuples, and we can't modify those. 

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
    # Loop over real rows, creating virtual rows. The invariant is that
    # curr <= vrow < next. When vrow catches up to next, discard curr,
    # make curr be next, and get another next. If timestamp of new next is
    # equal to curr, merge them and get another next.
    # Now that we are reading from ICG, merging should never happen.
    curr_row = rows.next()
    next_row = rows.next()
    curr_time = curr_row['rtime']
    next_time = next_row['rtime']
    if curr_time == next_time:
        raise Exception('before loop: next row time equals curr row time')
    vrow_time = curr_time
    delta5 = timedelta(minutes=5)
    global merged_rows          # should stay empty
    debug = False
    merged_rows = []
    # print('vrow_time',vrow_time,'next_time',next_time)
    try:
        # loop over vrows. Exit condition is when we get StopIteration from real rows
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
                    next_time = next_row['rtime']
                    if next_time > curr_time:
                        break
                    # merge from curr into next, since the top of the
                    # loop discards curr_row. Should not happen
                    merge_rows(curr_row, next_row)
            if vrow_time == curr_time:
                # yield a real row
                yield curr_row
            else:
                # yield a virtual row.
                vrow = {'rtime': vrow_time, 'real_row': 0, 'user': curr_row['user']}
                # fill in other fields with None
                for key in curr_row.iterkeys():
                    if key not in vrow:
                        vrow[key] = None
                yield vrow
            vrow_time = vrow_time + delta5
    except StopIteration:
        yield curr_row
        print '''Done generating virtual rows. End time is {end}
and we merged {nmerge} rows'''.format(
    end=curr_row['rtime'],
    nmerge=len(merged_rows))

def basal_amt_12(rows=None):
    '''This version processes virtual rows, with timestamps at 5 minute
intervals and the basals divided by 12 and trickled into every
row. Added under a new key, 'basal_amt_12'. The input is expected to
be complete, where every row has a basal_amt. However, there may be a
gap, determined by basal_gap == 1, in which case, basal_amt_12 will be
null (invalid) until the next valid basal_amt. So, there are 3 situations:
1) in a gap, so basal_amt_12 = None
2) null basal, so use previous valid basal
2) non-null basal_amt, so no longer in a gap
    '''
    prev_valid_basal = None
    in_gap = True               # start out this way
    for row in rows:
        row_basal = row_get(row,'basal_amt')
        start_gap = row_get(row,'basal_gap') == 1
        if start_gap or (in_gap and row_basal is None):
            in_gap = True
            prev_valid_basal = None
            row_set(row,'basal_amt_12',None)
        elif row_basal is None:
            if prev_valid_basal is None:
                raise Exception('prev_valid_basal is None but not in a gap')
            row_set(row,'basal_amt_12',prev_valid_basal / 12.0)
        else:
            # valid row_basal, so end of gap
            in_gap = False
            # print 'gap ends at ',row_get(row,'rtime')
            # change the current value based on this new setting
            prev_valid_basal = row_basal
            row_set(row,'basal_amt_12',prev_valid_basal / 12.0)
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

def read_carb_action_curves(test=True):
    '''Return the carb absorption curves as a dictionary of arrays,
projecting three columns of the spreadsheet (as a CSV file). The bls
column is replicated as breakfast, lunch, and snack, so that that we
can look up the curve using the carb_code.
    '''
    if test:
        print 'USING TEST CAC'
        CAC = {
            'rescue': [ 0, 0.5, 1.0, 0.75, 0.5, 0.25, 0 ],
            # symmetrical, short
            'bls': [ 0, 0.2, 0.5, 0.8, 1.0, 0.8, 0.5, 0.2, 0 ],
            # skewed, long
            'dinner': [ 0, 0.2, 0.5, 0.8, 1.0, 0.9, 0.8, 0.7, 0.5, 0.3, 0.2, 0.1, 0 ]
            }
    else:
        print 'USING REAL CAC'
        rescue_vals = []
        bls_vals = []
        dinner_vals = []
        with open(CAC_filename, 'rU') as csvfile:
            reader = csv.reader(csvfile) # default format is Excel
            headers = reader.next()
            print('CAC headers are '+str(headers))
            for row in reader:
                if row[1] != '':
                    rescue_vals.append(float(row[1]))
                if row[2] != '':
                    bls_vals.append(float(row[2]))
                if row[3] != '':
                    dinner_vals.append(float(row[3]))
            CAC = {'rescue': rescue_vals, 'bls': bls_vals, 'dinner': dinner_vals}
    # replicate the bls values
    CAC['breakfast'] = CAC['bls']
    CAC['lunch'] = CAC['bls']
    CAC['snack'] = CAC['bls']
    return CAC

def read_insulin_carb_smoothed(csvfile='insulin_carb_smoothed.csv',test=True):
    if test:
        csvfile = 'insulin_carb_smoothed_test1.csv'
    return csv_dict_generator(csvfile)

def compute_dynamic_insulin(rows=None,test_data=False,showCalc=False,test_iac=False):
    '''read rows and convolve the insulin values with
    insulin_action_curve (IAC) to get dynamic_insulin (DI), yielding the data
    assumes each row has basal_amt_12, total_bolus_volume, and dynamic_insulin
    '''
    # should update this to the shiftdown() technique; saves a lot of consing
    IAC = read_insulin_action_curve(test=test_iac)
    N = len(IAC)
    lastrows = []
    if rows is None:
        rows = read_insulin_carb_smoothed(test=test_data)
    print('in compute_dynamic_insulin, showCalc is {sc}'.format(sc=showCalc))

    def anynull(row_seq):
        for r in row_seq:
            if row_get(r,'basal_amt_12') is None:
                return True
        return False

    for row in rows:
        # print('row1',row)
            
        # because we're adding rows onto the front, that has the effect of time-reversing
        # the IAC
        lastrows.insert(0, row)
        if len(lastrows) > N:
            lastrows.pop()

        if anynull(lastrows):
            # in a gap, so null 
            row_set(row,'dynamic_insulin', None)
            yield row
        else:
            # not in a gap, so calc.
            incr = 0
            calc = []
            for i in xrange(min(N,len(lastrows))):
                prevrow = lastrows[i]
                ins_act = IAC[i]
                ins_in = ((row_get(prevrow,'basal_amt_12') or 0.0) +
                          (row_get(prevrow,'total_bolus_volume') or 0.0))
                if showCalc:
                    calc.append((ins_act,ins_in))
                incr += ins_act*ins_in
            # end of convolution, set the dynamic insulin for this new row
            row_set(row,'dynamic_insulin', incr)
            if showCalc:
                # the calc column no longer exists, but we can print it
                sys.stderr.write('di calc: {} total of {}\n'.format(calc,incr))
                # row_set(row,'active_insulin_calc', str(calc))
            # print('number of buffered rows: {n}'.format(n=len(lastrows)))
            yield row
    
def compute_dynamic_carbs(rows=None,showCalc=False,test_cac=False):
    '''read rows and convolve the carb values with the
    carb_absorption_curve (cac) for that carb_type to get dynamic
    carbs, yielding the data.  assumes each row has carbs, carb_code,
    and dynamic_carbs.
    '''
    # should update this to the shiftdown() technique; saves a lot of consing
    CAC = read_carb_action_curves(test=test_cac)
    # we'll treat after9 the same as dinner, and before6 the same as breakfast, so we do that here:
    CAC['after9'] = CAC['dinner']
    CAC['before6'] = CAC['breakfast']

    max_window = len(CAC['dinner'])
    lastrows = []
    sys.stderr.write('in dynamic_carbs, showCalc is {sc}\n'.format(sc=showCalc))
    carb_types = 'rescue before6 breakfast lunch snack dinner after9 '.split()

    for row in rows:
            
        # because we're adding rows onto the front, that has the effect of time-reversing
        # the CAC
        lastrows.insert(0, row)
        if len(lastrows) > max_window:
            lastrows.pop()

        # this adds to the dynamic_carb total the sum of the prior
        # carbs of the given type. So if you're still absorbing carbs
        # from lunch and a snack and dinner, there could be three
        # different contributions to the total dynamic carbs. This
        # function adds just one type of carbs.  
        def add_carb_type(carb_type):
            incr = 0
            calc = []
            for i in xrange(min(len(CAC[carb_type]), len(lastrows))):
                prevrow = lastrows[i]
                carb_absorp = CAC[carb_type][i]
                if row_get(prevrow,'carb_code') == carb_type:
                    carbs_in = row_get(prevrow,'carbs')
                else:
                    carbs_in = 0.0
                if showCalc:
                    calc.append((carb_absorp,carbs_in))
                incr += carb_absorp * carbs_in
            # after the loop, return the total carbs of this type
            if showCalc:
                if incr > 0:
                    sys.stderr.write('non-zero carbs of type {}: {} totalling {}\n'.format(carb_type,calc,incr))
                else:
                    sys.stderr.write('zero carbs of type {}\n'.format(carb_type))
            return incr

        dc = 0
        for carb_type in carb_types:
            dc += add_carb_type(carb_type)

        # end of convolution, set the dynamic carbs for this new row
        row_set(row,'dynamic_carbs', dc)
        yield row

# ================================================================

def random_cgm(rows):
    for row in rows:
        row['cgm'] = random.randint(80,100)
        yield row

def convert_dicts_to_lists(rows, keys=[]):
    for row in rows:
        yield [ row.get(k,0.0) for k in keys ]

def test_di(test_data=True, showCalc=True, test_iac=True, test_cac=True):
    global cursor_columns
    cursor_columns = test_data_cursor_columns
    g = pipe.pipe( lambda x: test_data2(),
                   lambda p: gen_insulin_carb_vrows(rows=p),
                   random_cgm,
                   lambda p: convert_dicts_to_lists(p,keys=cursor_columns),
                   basal_amt_12,
                   categorize_carbs,
                   compute_minutes_since,
                   compute_cgm_slopes,
                   lambda x: compute_dynamic_insulin(x,test_iac=test_iac, showCalc=False),
                   lambda x: compute_dynamic_carbs(x,test_cac=test_cac, showCalc=showCalc)
                   )
    print ','.join(cursor_columns)
    for row in g(None):
        if len(row) != len(cursor_columns):
            raise Exception('length mismatch {} versus {}'.format(row,cursor_columns))
        print ','.join([ str(x) for x in row ])
    
# ================================================================

def compute_minutes_since(rows):
    '''compute the minutes_since_last_meal and minutes_since_last_bolus
columns. Takes a row generator and returns a row generator.'''
    last_bolus_time = None
    last_meal_time = None
    for row in rows:
        carb_code = row_get(row,'carb_code')
        bolus_volume = row_get(row,'total_bolus_volume')
        this_time = row_get(row,'rtime')
        if bolus_volume is not None and bolus_volume > 0:
            last_bolus_time = this_time
        if carb_code is not None and carb_code != 'rescue':
            last_meal_time = this_time
        if last_bolus_time is not None:
            row_set(row,'minutes_since_last_bolus', (this_time-last_bolus_time).total_seconds()/60)
            # print 'set ...bolus to {} '.format(row_get(row,'minutes_since_last_bolus'))
        if last_meal_time is not None:
            row_set(row,'minutes_since_last_meal', (this_time-last_meal_time).total_seconds()/60)
        yield row

def test_compute_minutes_since():
    rows = gen_rows_ic(end='2014-05-01') # this gets more columns than we need, but maybe we can optimize that later
    global cursor_columns
    get_cursor_columns()
    col1 = cursor_columns.index('minutes_since_last_bolus')
    col2 = cursor_columns.index('minutes_since_last_meal')
    col3 = cursor_columns.index('rtime')
    conn = get_conn()
    num_rows = 0
    update = conn.cursor()
    for row in compute_minutes_since(rows):
        num_rows += 1
        if num_rows % 1000 == 0:
            print('updated ',num_rows)
        update.execute('update insulin_carb_smoothed set minutes_since_last_bolus = %s, minutes_since_last_meal = %s where rtime = %s',
                       [row[col1],row[col2],row[col3]])



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
    '''Get a 65 minute (13 row) window of data, checking the middle of it
for rescue events. Any carbs with insulin are a meal. Put categories
in the 'tags' column.

Dealing with end effects is important. In some cases, like if the
first row is carbs and insulin, we know it's a meal and we can
categorize it, but if the first row is carbs and no insulin, is it
rescue carbs or is it a meal and we just didn't get the insulin that
preceded? The only way to be sure in general is to trim off the first
(N-1)/2 == 6 rows and the last 6 rows. So, we only *yield* the rows
that are in the center of the window. We'll only be losing 12 rows out
of the hundreds of thousands that we have, and the algorithm is much
simpler.
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
            if row_get(s,'total_bolus_volume') > 0:
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
            if row_get(mid,'rec_nums') == '87789&87790':
                raise Exception('trouble!')
            # carbs are complicated
            if row_get(mid,'carbs') > 0:
                if anyInsulin(window):
                    name = meal_name(row_get(mid,'rtime'))
                    mealcounts[name] += 1
                    row_set(mid,'carb_code',name)
                    addTag(mid,name)
                else:
                    # print('FOUND RESCUE CARBS! at ',mid['rtime'])
                    rescue_carb_events += 1
                    addTag(mid,'rescue_carbs')
                    row_set(mid,'rescue_carbs', 1)
                    row_set(mid,'carb_code', 'rescue')
            if (row_get(mid,'carbs') > 0 and
                row_get(mid,'carb_code') not in ['before6','breakfast','lunch','snack','dinner','after9','rescue']):
                print row
                raise Exception('bad carb_code in categorize_carbs check: {}'.format(row_get(row,'carb_code')))
                    
            # corrective insulin
            if row_get(mid,'total_bolus_volume') > 0 and not anyCarbs(window):
                corrective_insulin_events += 1
                # print('FOUND RESCUE INSULIN! at ',mid['rtime'])
                addTag(mid,'corrective_insulin')
                row_set(mid,'corrective_insulin', 1)
            
            pipe.shift(window,initRow(rows.next()))
            yield mid
    except StopIteration:
        print '\ncategorize_carbs found {x} rescue_carb events and {y} corrective_insulin_events'.format(
            x=rescue_carb_events,
            y=corrective_insulin_events)
        print 'meal counts',mealcounts

def compute_cgm_slopes(rows=None):
    '''Get a 45 minute window of data, computing the cgm slopes for 10, 30 and 45 minute intervals and derivatives of that. Need to have a window of 10 rows (45 = 5 * 9). 
Formulas for slopes are current cgm - cgm from 2, 6 or 9 rows earlier.  
Formulas for derivatives are current slope - slope from 2, 6 or 9 rows earlier.  
    '''
    window = []
    winsize = 10                # number of rows in the window

    def slope(curr,col,offset):
        curr_val = row_get(curr,'cgm')
        prior = window[-1 - offset]
        prior_val = row_get(prior,'cgm')
        if curr_val is not None and prior_val is not None:
            row_set(curr,col,curr_val-prior_val)

    def derive(curr,src_col,dst_col,offset):
        curr_val = row_get(curr,src_col)
        prior = window[ -1 - offset ]
        prior_val = row_get(prior,src_col)
        if curr_val is not None and prior_val is not None:
            row_set(curr,dst_col,curr_val-prior_val)

    # init window
    while len(window) < winsize:
        window.append(rows.next())

    try:
        while True:
            curr = window[-1]
            slope(curr,'cgm_slope_10',2)
            slope(curr,'cgm_slope_30',6)
            slope(curr,'cgm_slope_45',9)
            derive(curr,'cgm_slope_10','cgm_derivative_10',2)
            derive(curr,'cgm_slope_30','cgm_derivative_30',6)
            derive(curr,'cgm_slope_45','cgm_derivative_45',9)

            # shift window
            out = window[0]
            pipe.shift(window,rows.next())
            yield out
    except StopIteration:
        for r in window:
            yield r

# ================================================================
# Output to database tables

def ic_output_dict(rows, tablename, keys):
    '''Write rows (can be an iterable) but each row is a dict not list to the given table'''
    conn = get_conn()
    curs = conn.cursor()
    # clear out old data
    curs.execute('delete from {table}'.format(table=tablename))
    sql = 'insert into {table}({cols}) values({vals})'.format(
        table=tablename,
        cols=','.join(keys),
        vals=','.join(['%s' for k in keys]))
    print('insert using ',sql)
    insert_count = 0
    for row in rows:
        insert_count += 1
        if insert_count % 10000 == 0:
            print 'ic_output_dict to {} '.format(tablename),str(insert_count)
        # this would also be more efficient if we kept things as lists throughout
        curs.execute(sql,[row[k] for k in keys])

def ic_output_list(rows, tablename, keys):
    '''Write rows to the given table. Rows can be an iterable. Each row is a list. '''
    conn = get_conn()
    curs = conn.cursor()
    # clear out old data
    curs.execute('delete from {table}'.format(table=tablename))
    sql = 'insert into {table}({cols}) values({vals})'.format(
        table=tablename,
        cols=','.join(keys),
        vals=','.join(['%s' for k in cursor_columns]))
    print('insert using ',sql)
    insert_count = 0
    for row in rows:
        insert_count += 1
        if insert_count % 10000 == 0:
            print 'ic_output_list to {} '.format(tablename),str(insert_count)
        curs.execute(sql,row)


def db_update_rtime(rows, tablename, keys=cursor_columns):
    '''Update rows (can be an iterable) to the given table'''
    conn = get_conn()
    curs = conn.cursor()
    curs.execute('select * from {table}'.format(table=tablename))
    global cursor_columns
    cursor_columns = [ desc[0] for desc in curs.description ]
    print '\n in db_update_rtime, cursor_columns is ',cursor_columns
    settings = ','.join( [ '{col} = %s'.format(col=key) for key in cursor_columns ] )
    curs = conn.cursor()
    sql = 'update {} set {} where rtime = %s'.format(tablename,settings)
    print('update using ',sql)
    insert_count = 0
    for row in rows:
        if len(row) != len(cursor_columns):
            raise Exception('row has wrong length')
        insert_count += 1
        if insert_count % 10000 == 0:
            print 'updated ',str(insert_count)
        data = list(row)
        data.append(row_get(row,'rtime')) # extra occurrence for the key
        curs.execute(sql,data)
    print 'done updating'

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

test_data_cursor_columns = 'user,rtime,basal_amt,basal_gap,basal_amt_12,total_bolus_volume,normal_insulin_bolus_volume,combination_insulin_bolus_volume,carbs,notes,minutes_since_last_meal,minutes_since_last_bolus,carb_code,real_row,rescue_carbs,corrective_insulin,tags,cgm,cgm_slope_10,cgm_slope_30,cgm_slope_45,cgm_derivative_10,cgm_derivative_30,cgm_derivative_45,dynamic_carbs,dynamic_insulin,rec_num'.split(',')

def test_data2():
    for row in [
        {'rtime': '2016-08-08 07:00', 'basal_amt': 3.0, 'total_bolus_volume': 0.0}, # start at zero
        {'rtime': '2016-08-08 08:00', 'basal_amt': 3.0, 'total_bolus_volume': 2.0}, # corrective insulin
        {'rtime': '2016-08-08 09:00', 'basal_amt': 3.0, 'total_bolus_volume': 1.0, 'carbs': 10.0}, # breakfast
        {'rtime': '2016-08-08 10:00', 'basal_amt': 3.0, 'total_bolus_volume': 0.0, 'carbs': 3.0}, # rescue carbs
        {'rtime': '2016-08-08 11:00', 'basal_amt': None, 'basal_gap': 1}, # gap starts
        {'rtime': '2016-08-08 12:00', 'basal_amt': 3.0}, # gap ends
        {'rtime': '2016-08-08 13:00', 'basal_amt': 1.0, 'total_bolus_volume': 2.0, 'carbs':10.0}, # lunch
        {'rtime': '2016-08-08 16:00', 'basal_amt': 1.0, 'total_bolus_volume': 2.0, 'carbs':5.0}, # snack
        {'rtime': '2016-08-08 18:00', 'basal_amt': 1.0, 'total_bolus_volume': 4.0, 'carbs':50.0}, # dinner
        {'rtime': '2016-08-09 01:00', 'basal_amt': 1.0, 'total_bolus_volume': 0.0} # last row
        ]:
        # print('draw from test data')
        row['user'] = 'hugh'
        if type(row['rtime']) == str:
            row['rtime'] = datetime.strptime(row['rtime'],RTIME_FORMAT)
        row['real_row'] = 1
        for k in test_data_cursor_columns:
            if k not in row:
                row[k] = None 
        row['cgm'] = random.randint(80,120)
        yield row
    
def test_data2_lists():
    global cursor_columns
    cursor_columns = test_data_cursor_columns
    for row in [
            ['2016-08-08 07:00', 0.0, 0, 0, 0.0, 0.0,0], # start at zero
            ['2016-08-08 08:00', 0.0, 0, 0, 2.0, 3.0,0], # corrective insulin
            ['2016-08-08 09:00', 0.0, 0, 0, 2.0, 3.0,0], # not rescue carbs or insulin
            ['2016-08-08 10:00', 0.0, 0, 0, 0.0, 3.0,0], # rescue carbs
            ['2016-08-08 11:00', 0.0, 0, 0, 0.0, 0.0,0] # last row
    ]:
        print('draw from test data')
        yield row

def create_virtual_rows(test=False,start=None,end=None):
    '''Reads from ICG and writes to ICS, inserting filler rows so that we have a row for every rtime'''
    if test:
        rows = test_data2
    else:
        rows = lambda : gen_rows_ic_dictionaries(tablename='insulin_carb_grouped',start=start,end=end)
    keys_from_icg()
    g = pipe.pipe( lambda x: rows(),
                   lambda p: gen_insulin_carb_vrows(rows=p), # does the actual smoothing
                   )
    # pipe.more(g(None))
    ic_output_dict(g(None),
                   'insulin_carb_smoothed',
                   IC_KEYS)

def pipe_write_ics2(test=False,start=None,end=None):
    '''Update the ICS table'''
    if test:
        raise Exception('NYI')
        rows = test_data2
    else:
        rows = lambda : gen_rows_ic(start=start,end=end)

    def cat(p):
        for v in p:
            yield v

    def check_carb_code(p,label):
        n = 0
        keys = 'rtime,carbs,carb_code,dynamic_carbs'.split(',')
        for row in p:
            n += 1
            if row_get(row,'rtime') == datetime(2017, 1, 1, 0, 35, 0) or n==1:
                print(n,label,[str(row_get(row,x)) for x in keys])
            if row_get(row,'rec_nums') == '87789&87790':
                raise Exception('trouble!')
            if (row_get(row,'carbs') > 0 and
                row_get(row,'carb_code') not in ['before6','breakfast','lunch','snack','dinner','after9','rescue']):
                print row
                raise Exception('bad carb_code in {} check: {}'.format(label,row_get(row,'carb_code')))
            yield row

    g = pipe.pipe( lambda x: rows(),
                   basal_amt_12,
                   categorize_carbs,
                   lambda x: check_carb_code(x,'one'),
                   compute_minutes_since, # has to be after categorize carbs, since that identifies meals
                   compute_cgm_slopes,
                   compute_dynamic_insulin,
                   lambda x: check_carb_code(x,'two'),
                   compute_dynamic_carbs,
                   lambda x: check_carb_code(x,'three'),
                   # lambda p: pipe.tee(p,prefix='x: ',stringify=lambda r: str(listify_row(r,IOB_KEYS))),
                   cat
                   # nonzerocarbs
                   )
    # pipe.more(g(None))
    ic_output_list(g(None),
                   'insulin_carb_smoothed_2',
                   cursor_columns)
    
def pipe_update_ics_meta(func):
    '''update the ICS table using func as filter'''
    db_update( func(gen_rows_ic()), 'insulin_carb_smoothed', IOB_KEYS)


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

def num_rows(conn=get_conn(),tablename='insulin_carb_smoothed'):
    curs = conn.cursor()
    curs.execute('select count(*) from {}'.format(tablename))
    row = curs.fetchone()
    return row[0]

## ================================================================

def join_bg_values():
    conn = get_conn()
    curs = conn.cursor()
    # this takes 18.71 seconds, so be patient
    curs.execute('''update insulin_carb_smoothed as ics inner join cgm_noduplicates as cgm using (rtime) 
                    set ics.cgm = cgm.mgdl''')
    # this only takes 0.77 seconds
    curs.execute('''update insulin_carb_smoothed as ics inner join mgm_noduplicates as mgm using (rtime) 
                    set ics.bg = mgm.mgdl''')

## ================================================================

def finish_insulin_carb_smoothed(start=None,end=None):
    print '='*30, 'create virtual rows'
    create_virtual_rows(start=start,end=end)
    print num_rows()
    print '='*30,'join bg values'
    join_bg_values()
    print num_rows()
    print '='*30,'starting pipe_write_ics2'
    pipe_write_ics2(start=start,end=end)
    print '='*30,'done'

## ================================================================

# New debugging stuff for 8/27

def icg(start='2017-01-01',end='2017-01-02'):
    conn = get_conn()
    curs = conn.cursor()
    get_cursor_columns(tablename='insulin_carb_grouped')
    curs.execute( ("select * from insulin_carb_grouped where rtime >= '{start}' and rtime <= '{end}' "
                   .format(start=start,end=end)))
    while True:
        row = curs.fetchone()
        if row is None:
            return
        yield row

def print_row2(row,cols):
    print ' | '.join([ str(row[i]) for i in cols ])

def prows(rows,cols='rtime,carbs,carb_code'):
    col_names = cols.split(',')
    indexes = [ cursor_columns.index(k) for k in col_names ]
    print ' | '.join(col_names)
    for row in rows:
        print ' | '.join( str(row[i]) for i in indexes )

def test_categorize_carbs(start='2017-01-01',end='2017-01-02'):
    rows = gen_rows_ic(start=start,end=end)
    before = list(rows)
    print '\n before \n'
    cols = [ cursor_columns.index(k) for k in 'rtime,carbs,carb_code'.split(',') ]
    for row in before:
        print_row2(row,cols)
    gen = (row for row in rows)
    g2 = categorize_carbs(gen)
    after = list(g2())
    print '\n after \n'
    for row in after:
        print_row2(row,cols)
    return after

def bad_row(label):
    conn = get_conn()
    curs = conn.cursor()
    rows = curs.execute("select * from insulin_carb_smoothed where rtime = '2014-03-14 17:15:00'")
    print label,'bad row is there'

## ================================================================

if __name__ == '__main__':
    # write_real_stuff()
    # pipe5(False)
    if len(sys.argv) > 1:
        if sys.argv[1] == 'test':
            test_di()
        else:
            start = (sys.argv[1])
            end = (sys.argv[2])
            finish_insulin_carb_smoothed(start=start,end=end)
    else:
        finish_insulin_carb_smoothed(None)
