'''An experiment to see what is the best way to iterate over "windows"
of rows in the database. That is, the worker function is called on
rows 1-N, 2-(N+1), ... K-(N+K).  We use this kind of idea to calculate
DI and DC. 

Ideas:

1. Keep an array of size K and slide values up the array by hand, then
pass the array to the worker.

2. Keep an array of size K and make the worker iterate from I to I+K,
wrapping around at K

3. Create an object with the ability to iterate over a circular array,
so that the worker can just use a FOR loop.

Seems like #2 has to be the most efficient, even if it messes up the
worker function.

What to do about starting? With DC, we can assume past carbs are all
zero. Should we do the same with DI? That's all in the past, so it
hardly matters. What about outages and such? I think we'll do the
same.  

Actually, the first stored value should be in row K. Or maybe K+1. The
first K-1 rows should all be NULL. But that requires extra
logic. Maybe keep it simple.

The database I/O is the dominating factor; none of the above
matters. At least option 2, which is what I did, avoids unnecessary
space consumption. The di_worker and di_driver functions shouldn't
generate any garbage.

It takes 24 seconds just to read in all 1M rows! The overall algorithm
on all 1M rows, that is, 1M updates, takes 11 minutes! That's 10K rows/minute.

But the results are a little surprising:

real    11m32.795s
user    2m53.056s
sys     1m15.594s

There are 8 node processes running at 100%, so maybe it would run
faster if the node processes weren't running. We only have one CPU.

This code is *not* ready for prime time, because the DI is computed
based *only* on bolus values. It doesn't include basal rates.

The architecture doesn't generalize well, yet, because the interface
to the worker isn't very generic. It would be easy to, say, compute DC
the same way, but other values might be tricky.

'''

import csv
import cs304dbi as dbi

def di_worker(window, index, iac):
    if len(window) != len(iac):
        raise ValueError('window and iac must be lists of the same length')
    win_width = len(iac)
    sum = 0 
    for i in range(win_width):
        # remember, iterate through IAC in reverse order
        j = (index - i) % win_width
        weight = iac[i]
        insulin = window[j]
        sum += weight * insulin
    return sum

ICS_TABLE = 'insulin_carb_smoothed_2' # 'ics_test'

def di_driver(conn, test_array, iac, min_rtime, max_rtime):
    if abs(1-sum(iac)) > 0.000001:
        raise ValueError('IAC does not sum to one')

    win_width = len(iac)
    window = [ 0 for w in iac ]
    index = -1
    # just for debugging
    total_insulin = 0
    total_di = 0 
    # get going
    if test_array:
        data = enumerate(test_array)
    else:
        curs = conn.cursor()
        sql = f'''SELECT rtime, total_bolus_volume FROM {ICS_TABLE}
                  WHERE rtime between %s and %s'''
        print(f'sql is {sql}')
        n = curs.execute(sql, [min_rtime, max_rtime])
        print(f'number of rows to process is {n}')
        data = curs.fetchall()
    # the real work
    for rtime, insulin in data:
        try:
            insulin = float(insulin)
        except:
            insulin = 0.0
        total_insulin += insulin
        # put data in next slot
        index = ( index + 1 ) % win_width
        window[index] = insulin
        di = di_worker(window, index, iac)
        total_di += di
        if test_array:
            test_array[rtime] = di
        else:
            curs.execute(f'''UPDATE {ICS_TABLE} SET dynamic_insulin = %s WHERE rtime = %s''',
                         [di, rtime])
            conn.commit()
    print(f'total insulin {total_insulin} total DI {total_di}')

def normalize(nums):
    total = sum(nums)
    return [ i/total for i in nums ]

IAC_1 = [0, 0.4, 0.3, 0.2, 0.1]
IAC_2 = normalize([0, 2, 5, 8, 6, 4, 3, 2, 1])

def di_driver_test():
    insulin_trace = [ 0 for i in range(50) ]
    insulin_trace[10] = 1
    insulin_trace[20] = 2
    # these will overlap with IAC_2
    insulin_trace[30] = 2
    insulin_trace[35] = 2
    copy = insulin_trace[:]
    di_driver(None, insulin_trace, IAC_1, None, None)
    for x,y in zip(copy, insulin_trace):
        print(f"{x}\t{y}")


def read_curve_from_csv(filename):
    '''This ignores column 1, which we assume is the time (0, 5,
    10...) and just returns the second column. It also skips the first
    row, since that will be the headers.'''
    curve = []
    with open(filename, 'r') as fin:
        reader = csv.reader(fin)
        next(reader)            # skip the header row
        for row in reader:
            x = int(row[0])
            y = float(row[1])
            curve.append(y)
    return curve
        

MIN_RTIME = '2014-01-01'
MAX_RTIME = '2025-01-01'

def main(iac_file='iac_sk_17_3_2024-05-31.csv',
         min_rtime=MIN_RTIME,
         max_rtime=MAX_RTIME):
    conn = dbi.connect()
    iac = read_curve_from_csv(iac_file)
    di_driver(conn, None, iac, min_rtime, max_rtime)
    
if __name__ == '__main__':
    main()
