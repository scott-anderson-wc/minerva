#!/usr/bin/python

# This script processes the _1 version, which omits missing data, into the
# first regularized version of the insulin_carb and cgm tables, the _2
# version, which regularizes the timestamp.

# this script is not currently used, as the process_2.sql file is easier and more efficient.
exit

import MySQLdb
import dbconn2
from datetime import datetime, timedelta

dbconn = None

def dictCursor():
    global dbconn
    dsn = dbconn2.read_cnf('/home/hugh9/.my.cnf')
    dsn['db'] = 'janice'
    dbconn = dbconn2.connect(dsn)
    curs = dbconn.cursor(MySQLdb.cursors.DictCursor)
    return curs

# This can be made more efficient when doing a zillion conversions, but it's fast enough for now.
# Actually, it's 37s for 22K entries, so it really ought to be speeded up a little.

def insert_dict(curs, table_name, row):
    cols = row.keys()
    qmks = [ '%s' for c in cols ]
    sql = 'insert into ' + table_name + '(' + ','.join(cols) + ') values (' + ','.join(qmks) + ')'
    vals = [ row[c] for c in cols ]
    curs2.execute(sql,vals)
    
## ================================================================
## main

curs = dictCursor()
# to make the code idempotent, we delete anything that might be there
curs.execute('''delete from insulin_carb_2''')

curs.execute('''select * from insulin_carb_1''')
curs2 = dbconn.cursor(MySQLdb.cursors.DictCursor)
while True:
    row = curs.fetchone()
    if row == None:
        break
    d = datetime.strptime(row['date_time'],'%Y%m%d%H%M')
    row['date_time'] = d
    row.pop('date')
    row.pop('epoch_time')
    insert_dict(curs2, 'insulin_carb_2', row)

# to make the code idempotent, we delete anything that might be there
curs.execute('''delete from cgm_2''')

'''
curs.execute('select * from cgm_1')
curs2 = dbconn.cursor(MySQLdb.cursors.DictCursor)
while True:
    row = curs.fetchone()
    if row == None:
        break
    d = datetime.strptime(row['time'],'%Y%m%d%H%M')
    row['date_time'] = d
    row.pop('time')
    row.pop('epoch_time')
    insert_dict(curs2, 'cgm_2', row)
'''

curs.execute('''insert into cgm_2(user,date_time,mgdl,rec_num)
select user, str_to_date(time,'%m/%d/%Y %H:%M'), mgdl, rec_num from cgm_1''')
