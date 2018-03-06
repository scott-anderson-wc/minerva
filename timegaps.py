import MySQLdb
import dbconn2
from iob2 import get_dsn, get_conn

def gen_row_pairs(query='select rec_num, date_time from cgm_2 order by rec_num',
                  conn=get_conn()):
    curs = conn.cursor(MySQLdb.cursors.DictCursor) # results as Dictionaries
    curs.execute(query)
    prev = curs.fetchone()
    while True:
        curr = curs.fetchone()
        if curr is None:
            break
        yield (prev,curr)
        prev = curr

def check_all_consecutive(rows):
    missing_rows = []
    for pair in rows:
        (a,b) = pair
        if a['rec_num'] != (b['rec_num'] - 1):
            print missing_rows, pair
            missing_rows.append(pair)
    print 'There ',len(missing_rows),' gaps'
    for pair in missing_rows:
        (a,b) = pair
        print ('{a_rec} (on {a_date}) to {b_rec} (on {b_date})'
               .format(a_rec=a['rec_num'],a_date=a['date_time'],
                       b_rec=b['rec_num'],b_date=b['date_time']))
    return missing_rows

def check_non_increasing_dates(rows):
    non_increasing_rows = []
    for pair in rows:
        (a,b) = pair
        if a['date_time'] > b['date_time'] - 1:
            non_increasing_rows.append(pair)
    return non_increasing_rows


    
