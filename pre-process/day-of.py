import sys
import MySQLdb
import dbconn2
import json
import datetime

TABLE = 'insulin_carb_2'

dsn = dbconn2.read_cnf()
conn = dbconn2.connect(dsn)

class DatetimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        return json.JSONENCODER.default(self, obj)

def test_json():
    json.dumps(datetime.datetime.now(),cls=DatetimeEncoder)


def row_iter(query):
    curs = conn.cursor(MySQLdb.cursors.DictCursor)
    numrows = curs.execute(query)
    print 'total of {} rows'.format(numrows)
    while True:
        row  = curs.fetchone()
        if row is None:
            raise StopIteration
        yield row

def day_of(focal_rec_num):
    curs = conn.cursor(MySQLdb.cursors.DictCursor)
    num_rows = curs.execute('SELECT date(date_time) as date FROM {} WHERE rec_num = %s'.format(TABLE),
                            [focal_rec_num])
    if num_rows > 0:
        row = curs.fetchone()
        focal_date = row['date']
        curs.execute('''SELECT date_time, basal_amt, bolus_type, bolus_volume, duration, carbs, notes, rec_num
                      FROM {}
                      WHERE date(date_time) = %s'''.format(TABLE),
                     [focal_date])
        rows = curs.fetchall()
        print '{} records for {}'.format(len(rows),focal_date)
        return json.dumps(rows, sort_keys=True, indent=4, cls=DatetimeEncoder)

if len(sys.argv) < 2:
    print 'Usage: {} rec_num'.format(sys.argv[0])
    print 'prints all the records of the date containing that rec_num'
else:
    print day_of(sys.argv[1])
