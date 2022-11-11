from datetime import datetime, timedelta
import dateutil.parser

mysql_fmt = '%Y-%m-%d %H:%M:%S'
mysql_fmt_dateonly = '%Y-%m-%d'

def mysql_datetime_to_python_datetime(datestr):
    '''Converts a string in MySQL datetime format into a Python datetime object'''
    # this makes it idempotent. Probably unnecessary, but nice.
    if type(datestr) == datetime:
        return datestr
    try:
        return datetime.strptime(datestr, mysql_fmt)
    except ValueError:
        # try w/o the time part
        return datetime.strptime(datestr, mysql_fmt_dateonly)

def python_datetime_to_mysql_datetime(datestr):
    '''Converts a Python datetime object to a a string in MySQL datetime format'''
    # this makes it idempotent. Probably unnecessary, but nice.
    if type(datestr) == str:
        return datestr
    return datetime.strftime(datestr, mysql_fmt)

def str(python_datetime_object):
    '''Given a Python Datetime object, returns a readable str in MySQL syntax'''
    return python_datetime_to_mysql_datetime(python_datetime_object)

def dstr(python_datetime_object):
    '''Given a Python Datetime object, returns a readable str in MySQL syntax'''
    return python_datetime_to_mysql_datetime(python_datetime_object)

def to_datestr(date,time=None):
    '''returns a MySQL datetime string YYYY-MM-DD HH:MM:SS and a Python datetime
from a human date and time.
time can be omitted, defaulting to 00:00:00 and can omit seconds, defaulting to 00'''
    if time is None:
        time = '00:00:00'
    elif time.count(':') == 1:
        time += ':00'

    dt_str = date + ' ' + time
    # This will throw an error if the datetime value are bogus.
    dt = datetime.strptime(dt_str,mysql_fmt)
    return dt.strftime(mysql_fmt),dt

def to_datetime(date):
    '''Converts a date string into a Python datetime object. Idempotent.'''
    if type(date) == datetime:
        return date
    # return mysql_datetime_to_python_datetime(date)
    return dateutil.parser.parse(date)

# rtime is time rounded *down* to the most recent 5 minute mark
# see the date5f function defined in pre-process/process_2.sql

def to_rtime(date):
    '''Returns a new datetime object (datetimes are immutable) with the
    minutes rounded down to the most recent five minute mark'''
    date = to_datetime(date)
    min_5 = ( date.minute // 5 ) * 5
    # notice the zero for the seconds
    rtime = datetime(date.year, date.month, date.day, date.hour, min_5, 0)
    return rtime

def to_rtime_round(dt):
    '''Returns a new datetime object (datetimes are immutable) with the
    minutes rounded to the most recent five minute mark    '''
    # convert to number of minutes (as a float) since the beginning of
    # the year then round that to the nearest multiple of 5 and
    # finally convert back to a date
    dt = to_datetime(dt)
    year_start = datetime(dt.year, 1, 1)
    td_seconds = dt - year_start   # this is a timedelta object
    seconds = td_seconds.total_seconds()
    mins = seconds / 60.0
    min_5 = 5 * round(mins / 5.0)
    rtime = year_start + timedelta(minutes=min_5)
    return rtime

def test_to_rtime_round():
    vals = [ '2022-06-17 00:20:44',
             '2022-06-17 00:20:41',
             '2022-06-17 00:20:42',
             '2022-06-17 00:20:49',
             '2022-06-17 00:20:41',
             '2022-06-17 00:20:42',
             '2022-06-17 00:19:56',
             '2022-06-17 00:19:51']
    for v in vals:
        print(to_rtime_round(v))

if __name__ == '__main__':
    def test(d,t):
        try:
            print(('{} {} \t=> {}'.format(d,t,to_datestr(d,t))))
        except:
            print(('{} {} \traises an exception'.format(d,t)))
    to_datestr('2018-01-01','05:50:00')
    test('2018-01-01','05:50:00')
    test('2018-01-01','05:50')
    test('2018-01-01',None)
    test('2018-01-01','05:65')
    test('2018-15-01','05:55')
    x,y = to_datestr('2018-01-01','05:50:00')
    print(('y is ',y))
    page_title = ('''ISF for {dt:%A}, {dt:%B} {dt.day}, {dt.year},
                     at {dt.hour}:{dt.minute:02d}'''
                  .format(dt=y))
    print((x, page_title))
    # ================================================================
    print('testing conversions to/from mysql and python')
    d1 = mysql_datetime_to_python_datetime('2019-01-22 13:24:00')
    print((d1, python_datetime_to_mysql_datetime(d1)))

