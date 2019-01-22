from datetime import datetime

mysql_fmt = '%Y-%m-%d %H:%M:%S'

def mysql_datetime_to_python_datetime(datestr):
    '''Converts a string in MySQL datetime format into a Python datetime object'''
    # this makes it idempotent. Probably unnecessary, but nice.
    if type(datestr) == datetime:
        return datestr
    return datetime.strptime(datestr, mysql_fmt)

def python_datetime_to_mysql_datetime(datestr):
    '''Converts a Python datetime object to a a string in MySQL datetime format'''
    # this makes it idempotent. Probably unnecessary, but nice.
    if type(datestr) == str:
        return datestr
    return datetime.strftime(datestr, mysql_fmt)

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

if __name__ == '__main__':
    def test(d,t):
        try:
            print('{} {} \t=> {}'.format(d,t,to_datestr(d,t)))
        except:
            print('{} {} \traises an exception'.format(d,t))
    to_datestr('2018-01-01','05:50:00')
    test('2018-01-01','05:50:00')
    test('2018-01-01','05:50')
    test('2018-01-01',None)
    test('2018-01-01','05:65')
    test('2018-15-01','05:55')
    x,y = to_datestr('2018-01-01','05:50:00')
    print 'y is ',y
    page_title = ('''ISF for {dt:%A}, {dt:%B} {dt.day}, {dt.year},
                     at {dt.hour}:{dt.minute:02d}'''
                  .format(dt=y))
    print x, page_title
    # ================================================================
    print 'testing conversions to/from mysql and python'
    d1 = mysql_datetime_to_python_datetime('2019-01-22 13:24:00')
    print d1, python_datetime_to_mysql_datetime(d1)
    
