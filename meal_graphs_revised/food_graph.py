'''Given dates of meals we are interested in, 
search the insulin_carb_smooth_2 table to get the
post-meal CGM values as lists of floats.

'''

import MySQLdb
import dbconn2
from datetime import datetime, timedelta,date, time
from dbi import get_dsn, get_conn # connect to the database
import fd_query as fd 

def post_meal_cgm(conn, meal_date, meal, duration):
    '''Returns the CGM values after the meal on meal_date for `duration`, which 
is a number of minutes, so 6*60 for 6 hours'''
    curs = conn.cursor(MySQLdb.cursors.DictCursor)
    three_hour_interval = [0]*36
    # returns the times that dinner start that day. Should be one entry but sometimes more
    # and sometimes none
    curs.execute('''select rtime from insulin_carb_smoothed_2 
                    where date(rtime)= %s and carb_code=%s ''',
                     [meal_date, meal])
    times = curs.fetchall()
    if len(times) == 0:
        print('no {} meal on {}'.format(meal,meal_date))
        return None
    # For now, use the last timestamp. TODO: analyze this more and choose the better time
    meal_start = times[0]['rtime']
    meal_end = meal_start + timedelta(minutes=duration)
    # get the post-meal data for the desired interval
    curs.execute('''select cgm
                    from insulin_carb_smoothed_2 
                    where rtime between %s and %s''',
                 [meal_start, meal_end])
    rows = curs.fetchall()
    cgm_vals = [ r['cgm'] for r in rows ]
    if None in cgm_vals:
        print('missing values in post-meal cgm for {}'.format(meal_date))
    return cgm_vals
    
def post_meal_cgm_traces_for_dates(conn, dates, meal, duration):
    '''Return a list of all the cgm_traces for the given dates, a list'''
    traces = []
    for date in dates:
        trace = post_meal_cgm(conn, date, meal, duration)
        if trace is not None:
            traces.append(trace)
    return traces

def average_cgm_trace(traces):
    '''Compute and return average CGM value from a list of traces.'''
    average = []
    lens = [ len(trace) for trace in traces ]
    n = min(lens)
    if n != max(lens):
        print('different length traces; skipping average')
        return None
    for i in range(n):
        sum = 0
        cnt = 0
        for trace in traces:
            cgm = trace[i]
            if cgm is not None:
                sum += cgm
                cnt += 1
        avg = sum / float(cnt)
        average.append(avg)
    return average

def post_meal_cgm_traces_between_dates(startDate, endDate, meal, duration,
                                       food_items_include, food_items_exclude):
    '''returns values: 
* an average trace of all dates in group with
* an average trace of all dates in group_complement
* list of traces of all dates in group_with
* list of traces of all dates in group_complement
* a list of date objects for dates in group with
* a list of date objects for dates in group_complement

TODO need to update and improve this docstring'''
    startDate = datetime.strptime(startDate, '%Y-%m-%d')
    endDate = datetime.strptime(endDate, '%Y-%m-%d')
    conn = get_conn()
    curs = conn.cursor(MySQLdb.cursors.DictCursor)
    # this is for context. Both groups are drawn from this list. Might want to
    # display it on the page somehow. TODO
    all_dates = fd.all_dates(conn,startDate,endDate,meal)
    print('num meals of that kind in the interval: {}'.format(len(all_dates)))
    # the list of dates that we are interested in
    group_with = fd.get_meal_dates(conn, startDate, endDate, meal, food_items_include, food_items_exclude)
    # the other dates; short for complement
    group_comp = fd.get_complement_dates(conn, startDate, endDate, meal, group_with)

    traces_with = post_meal_cgm_traces_for_dates(conn, group_with, meal, duration)
    traces_comp = post_meal_cgm_traces_for_dates(conn, group_comp, meal, duration)
    print('num traces in complement: {}'.format(len(traces_comp)))
    avg_with = average_cgm_trace(traces_with)
    avg_comp = average_cgm_trace(traces_comp)
    print('date type: ',type(group_with[0]))
    print('date_compe type: ',type(group_comp[0]))
    print('dates_with',[str(d) for d in group_with])
    print('dates_comp',[str(d) for d in group_comp])
    return avg_with, avg_comp, traces_with, traces_comp, group_with, group_comp

if __name__ == '__main__':
    post_meal_cgm_traces_between_dates(
        '2016-04-02', '2016-05-02', 'dinner', 3*60, ['avocado'], [])
