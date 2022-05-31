'''This is an experiment on (1) using generators for iterating over
the rows of the ics2 (insulin_carb_smoothed_2) table, which has so
many rows that fetching them all as dictionaries causes Python to
crash, and (2) accessing elements of a tuple using names instead of
numeric indexes.

The generators hide a series of SQL queries that get a batch of rows
into a local cache and return them one by one.

The accessor functions either search the description sequence for the
correct index or use a cached dictionary to get a numeric index, and
then use the index. There's also a function to return the numeric
index, so that the caller can just use that from now on. That would be
faster in general.

None of this is yet in use in most of the system, but I'm still hoping
to do that sometime.

Scott 
July 2010

'''


import collections
import pymysql
import cs304dbi as dbi

def getConn():
    dsn = dbi.cache_cnf()
    conn = dbi.connect()
    # this connection doesn't do auto-commit. Should it?
    return conn

def all_rows_as_dictionaries(conn=getConn()):
    '''This will often fail because of insufficient memory.'''
    curs = dbi.dictCursor(conn)
    curs.execute('select * from insulin_carb_smoothed_2')
    for row in curs.fetchall():
        yield row

def all_rows_as_tuples(conn=getConn()):
    '''This should not fail'''
    curs = dbi.cursor(conn)
    curs.execute('select * from insulin_carb_smoothed_2')
    for row in curs.fetchall():
        yield row
    

def index_for(curs, column):
    desc = curs.description
    for i in range(len(desc)):
        if desc[i][0] == column:
            return i
    raise ValueError('not among the columns in this query: {}'.format(column))

def total_cgm_dictionaries():
    conn = getConn()
    curs = dbi.dict_cursor(conn)
    curs.execute('select * from insulin_carb_smoothed_2 where year(rtime) < 2015')
    sum = 0
    for row in curs.fetchall():
        sum += row['cgm'] if row['cgm'] is not None else 0
    return sum

def total_cgm_tuples():
    conn = getConn()
    curs = dbi.cursor(conn)
    curs.execute('select * from insulin_carb_smoothed_2')
    cgm_index = index_for(curs, 'cgm')
    sum = 0
    for row in curs.fetchall():
        sum += row[cgm_index] if row[cgm_index] is not None else 0
    return sum

def total_cgm_short_tuples():
    '''This doesn't use generators, so it lets us check the 
calculations of the versions that do use generators.'''
    conn = getConn()
    curs = dbi.cursor(conn)
    curs.execute('select cgm from insulin_carb_smoothed_2')
    cgm_index = index_for(curs, 'cgm')
    sum = 0
    for row in curs.fetchall():
        sum += row[cgm_index] if row[cgm_index] is not None else 0
    return sum

def batch_query(size):
    '''Return a generator of tuples with given batch size
For size    1000, the time was 3m9
For size   10000, the time was 57.7s
For size  100000, the time was 44.5s
For size 1000000, python is killed
    '''
    conn = getConn()
    curs = dbi.cursor(conn)
    max_row = 477147
    start = 0
    for start in range(0,max_row,size):
        curs.execute('''select * from insulin_carb_smoothed_2 
                        where row >= {} 
                        limit {}'''.format(start,size))
        for row in curs.fetchall():
            yield row

def model_query_with_row_num():
    conn = getConn()
    curs = dbi.cursor(conn)
    max_row = 477147+1
    n = 0
    sum = 0
    size = 10000
    for start in range(0,max_row,size):
        curs.execute('''select cgm,dynamic_insulin,row from insulin_carb_smoothed_3
                        where row > {} 
                        limit {}'''.format(start,size))
        cgm_index,di_index,row_index = 0,1,2
        for row in curs.fetchall():
            # yield row
            cgm,di,row = row
            n += 1
            sum += cgm if cgm is not None else 0
        # print([start,n,sum])
    print(('num rows is {} total cgm is {}'.format(n,sum)))

def model_query_with_limit():
    conn = getConn()
    curs = dbi.cursor(conn)
    max_row = 477147+1
    n = 0
    sum = 0
    size = 10000
    for start in range(0,max_row,size):
        curs.execute('''select cgm,dynamic_insulin,row from insulin_carb_smoothed_3
                        limit {},{}'''.format(start,size))
        cgm_index,di_index,row_index = 0,1,2
        for row in curs.fetchall():
            # yield row
            cgm,di,row = row
            n += 1
            sum += cgm if cgm is not None else 0
        # print([start,n,sum])
    print(('num rows is {} total cgm is {}'.format(n,sum)))


def model_query_with_limit_without_max():
    conn = getConn()
    curs = dbi.cursor(conn)
    n = 0
    sum = 0
    size = 100000
    start = 0
    while True:
        num_rows = curs.execute('''select cgm,dynamic_insulin,row from insulin_carb_smoothed_3
                                   limit {},{}'''.format(start,size))
        # interesting code
        cgm_index,di_index,row_index = 0,1,2
        for row in curs.fetchall():
            # yield row
            cgm,di,row = row
            n += 1
            sum += cgm if cgm is not None else 0
        # print([start,n,sum])
        # end of interesting code; set up for next iteration
        if num_rows < size:
            break
        start += size
    # end of while
    print(('num rows is {} total cgm is {}'.format(n,sum)))


# ================================================================
# iteration with generator

def query_all(sql,vals):
    conn = getConn()
    curs = dbi.cursor(conn)
    size = 100000
    start = 0
    n = 0
    while True:
        num_rows = curs.execute(sql+(' limit {},{}'.format(start,size)),
                                vals)
        for row in curs.fetchall():
            n += 1
            yield row
        if num_rows < size:
            break
        start += size
    # end of while
    print(('finished query; number of rows yielded: {}'.format(n)))
    
def model_query_using_generator():
    n = 0
    sum = 0
    for row in query_all('select cgm,dynamic_insulin,row from insulin_carb_smoothed_3',[]):
        cgm,di,row = row
        n += 1
        sum += cgm if cgm is not None else 0
    print(('num rows is {} total cgm is {}'.format(n,sum)))


# ================================================================
# iteration with callback

def query_all_callback(sql,vals,callback):
    conn = getConn()
    curs = dbi.cursor(conn)
    size = 100000
    start = 0
    n = 0
    while True:
        num_rows = curs.execute(sql+(' limit {},{}'.format(start,size)),
                                vals)
        for row in curs.fetchall():
            n += 1
            callback(row)
        if num_rows < size:
            break
        start += size
    # end of while
    print(('finished query; number of callbacks: {}'.format(n)))
    
def model_query_using_callback():
    n = 0
    sum = 0
    def cb(row):
        nonlocal n, sum
        cgm,di,row = row
        n += 1
        sum += cgm if cgm is not None else 0
    # use callback
    query_all_callback('select cgm,dynamic_insulin,row from insulin_carb_smoothed_3',[],cb)
    print(('num rows is {} total cgm is {}'.format(n,sum)))


# ================================================================
# a moving window, using a deque

def model_window():
    deque = collections.deque([],24) # left-right increasing rtime
    num_windows = 0
    n = 0
    sum = 0
    stats = {}
    rtime_index = 0
    cgm_index = 1
    for row in query_all('select rtime,cgm,dynamic_insulin,row from insulin_carb_smoothed_3',[]):
        deque.append(row)
        if len(deque) < 24:
            print('continuing')
            continue
        # interesting code
        num_windows += 1
        if num_windows % 50000 == 0:
            print(('window: {}'.format(num_windows)))
            for elt in deque:
                print(('\t',elt))
        # business
        rtime,cgm,di,row = deque[0]
        n += 1
        sum += cgm if cgm is not None else 0
        first = deque[0][rtime_index]
        last = deque[-1][rtime_index]
        diff = (last-first).seconds/60
        stats[diff] = 1 + stats.get(diff,0)
        # end of for loop, pop leftmost item so there is room to add to the end
        deque.popleft()
    # after window loop
    print(('num rows is {} total cgm is {}'.format(n,sum)))
    print(('num_windows: {} and stats: {}'.format(num_windows,stats)))

def query_with_moving_window(window_size, sql, vals=[]):
    deque = collections.deque([],window_size) # left-right increasing rtime
    num_windows = 0
    for row in query_all(sql, vals):
        deque.append(row)
        if len(deque) < 24:
            continue
        # interesting code
        num_windows += 1
        yield deque
        # end of for loop, pop leftmost item so there is room to add to the end
        deque.popleft()
    print(('number of windows yielded: {}'.format(num_windows)))

def model_query_with_moving_window():
    n = 0
    sum = 0
    stats = {}
    rtime_index = 0
    for deque in query_with_moving_window(24,'select rtime,cgm,dynamic_insulin,row from insulin_carb_smoothed_3',[]):
        rtime,cgm,di,row = deque[0]
        n += 1
        sum += cgm if cgm is not None else 0
        first = deque[0][rtime_index]
        last = deque[-1][rtime_index]
        diff = (last-first).seconds/60
        stats[diff] = 1 + stats.get(diff,0)
    # done. Process entries from last deque
    sum -= cgm if cgm is not None else 0
    for row in deque:
        rtime,cgm,di,_ = row
        sum += cgm if cgm is not None else 0
    print(('total_cgm: {} and stats: {}'.format(sum,stats)))


if __name__ == '__main__':
    import sys
    import time
    if len(sys.argv) < 2:
        print('usage: script a-z\nwhere the letter chooses one of the test cases')
        sys.exit()
    print((sys.argv[1]))
    if sys.argv[1] == 'a':
        all_rows_as_dictionaries()
    if sys.argv[1] == 'b':
        results = all_rows_as_tuples()
    if sys.argv[1] == 'c':
        print((total_cgm_dictionaries()))
    if sys.argv[1] == 'd':
        t1 = time.time()
        print((total_cgm_tuples()))
        t2 = time.time()
        print((total_cgm_short_tuples()))
        t3 = time.time()
        print(( t2-t1, t3-t2 ))
    if sys.argv[1] == 'e':
        sum = 0
        for row in batch_query(1000000):
            cgm = (row[20])
            sum += cgm if cgm is not None else 0
            print(sum)
    if sys.argv[1] == 'f':
        print('case 6')
        conn = getConn()
        curs=conn.cursor()
        curs.execute('select * from insulin_carb_smoothed_2')
        print((len(curs.fetchall())))
    if sys.argv[1] == 'g':
        '''using ICS3 and a batch size of 100,000:
row_num was 8.8 and using limit was 9.2
with a batch size of 10,000, 
row_num was 9.1 and using limit was 13.5

so a little bit worse, but more modular'''
        t1 = time.time()
        model_query_with_row_num()
        t2 = time.time()
        model_query_with_limit()
        t3 = time.time()
        print(('time using row_num: {}\ntime using limit: {}\n'.format(t2-t1,t3-t2))) 
    if sys.argv[1] == 'h':
        model_query_with_limit()
        model_query_with_limit_without_max()
    if sys.argv[1] == 'i':
        t1 = time.time()
        model_query_with_limit_without_max()
        t2 = time.time()
        model_query_with_moving_window()
        t3 = time.time()
        print(('time w/o window: {}\n time w/ window: {}'.format(t2-t1, t3-t2)))
        # result: 15 seconds versus 9, so longer, but reasonably so
    if sys.argv[1] == 'j':
        t1 = time.time()
        model_query_with_limit_without_max()
        t2 = time.time()
        model_query_using_generator()
        t3 = time.time()
        model_query_using_callback()
        t4 = time.time()
        print(('time using first way: {}\ntime using generator: {}\ntime using callback: {}'.format(t2-t1,t3-t2,t4-t3)))
