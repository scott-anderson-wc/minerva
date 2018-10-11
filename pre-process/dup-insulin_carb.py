'''Python script to look a consecutive rows of insulin_carb with
identical timestamps to see if they can be combined because of any
pair of fields, only one is interesting (not null or empty string or
zero).  Only reads the data.

'''

import MySQLdb
import dbconn2

def row_iter(query):
    dsn = dbconn2.read_cnf()
    conn = dbconn2.connect(dsn)
    curs = conn.cursor(MySQLdb.cursors.DictCursor)
    numrows = curs.execute(query)
    print 'total of {} rows'.format(numrows)
    while True:
        row  = curs.fetchone()
        if row is None:
            raise StopIteration
        yield row

def check_dups():
    rows = row_iter('''SELECT date_time, basal_amt, bolus_type, bolus_volume, duration, carbs, notes, rec_num
                       from insulin_carb_2
                       where date_time in (select date_time
                                           from insulin_carb_2
                                           group by date_time
                                           having count(*) > 1)''')
    prev = rows.next()
    rownum = 0
    allrows = list(rows)
    nr = len(allrows)
    for row in allrows:
        rownum += 1
        # print 'row {}/{}'.format(rownum,nr)
        if prev['date_time'] != row['date_time']:
            prev = row
        else:
            # compare them
            for field in 'basal_amt bolus_type bolus_volume duration carbs notes'.split():
                if (prev[field] != None and row[field] != None and
                    prev[field] != '' and row[field] != '' and
                    prev[field] != 0 and row[field] != 0 and
                    prev[field] != row[field]):
                    print ('{} ({} and {}) disagree on {}: {} versus {}'
                           .format(row['date_time'],
                                   prev['rec_num'],row['rec_num'],
                                   field,
                                   prev[field], row[field]))

check_dups()
