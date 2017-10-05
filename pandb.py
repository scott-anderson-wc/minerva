# This file is a database interface using Pandas dataframes as the
# primary datastructure for sets of records from the database.


import pandas
import MySQLdb
import datetime
import dbconn2
import math
import flask
import util
import plotly
import plotly.plotly as py
import plotly.graph_objs as go

class StepException(Exception):
    pass


def to_date(date_str):
    if type(date_str) == type(datetime.datetime.today()):
        return date_str
    for fmt in ['%Y-%m-%d', '%Y%m%d', '%m/%d/%y']:
        try:
            return datetime.datetime.strptime(date_str, fmt)
        except:
            pass
    raise ValueError('Could not understand this date_str: ' + date_str)

def test_to_date():
    d1 = to_date('2016-04-03')
    d2 = to_date('20160403')
    d3 = to_date('4/3/16')
    to_date(d1)

def get_db_connection():
    dsn = dbconn2.read_cnf('/home/hugh9/.my.cnf')
    db_connection = dbconn2.connect(dsn)
    return db_connection

def get_ic_for_date(date_str, conn=get_db_connection(), meal_str='supper'):
    '''returns a pandas.dataframe for the given date and meal. If the
meal_str doesn't match one of the known values (breakfast, lunch,
supper), returns all records for that date.'''
    today = to_date(date_str)
    tomorrow = today+datetime.timedelta(days=1)
    time = meal_to_time_range(meal_str)
    # I added a clause to get data from the next day, so this will work for supper
    query = ('''select * from insulin_carb_2 where 
                date(date_time) = '{today}' or 
                date(date_time) = '{tomorrow}' and time(date_time) < '03:00' '''
             .format(today=today.strftime('%Y-%m-%d'),
                     tomorrow=tomorrow.strftime('%Y-%m-%d')))
    print query
    df = pandas.read_sql(query,
                         conn,
                         parse_dates = ['date_time'])
    return df

def meal_to_time_range(meal_name):
    '''return a pair of datetime values bounding the given meal'''
    # this definition leaves out some times. Anything left out will be
    # a snack, though I'm not sure how we search for those
    if meal_name == 'breakfast':
        return (datetime.time(0,0), datetime.time(11,0))
    elif meal_name == 'lunch':
        return (datetime.time(11,0), datetime.time(13,0))
    elif meal_name == 'supper':
        return (datetime.time(17,30), datetime.time(21,30))
    else:
        return 'true'


def select(df,cond_func):
    '''returns a new dataframe, a subset of df, with just the records satisfying 'cond_func'.'''
    recs = [ row._asdict() for row in df.itertuples() if cond_func(row) ]
    return pandas.DataFrame( recs, columns = df.columns )

def select_between_times(df,start,end):
    '''returns a new dataframe, a subset of df, with just the records between the given times.'''
    if type(start) != pandas.Timestamp:
        raise TypeError('start time is not a Timestamp: ',start)
    if type(end) != pandas.Timestamp:
        raise TypeError('end time is not a Timestamp: ',end)
    recs = [ row._asdict() 
             for row in df.itertuples()
             if row.date_time >= start and row.date_time <= end ]
    return pandas.DataFrame( recs, columns = df.columns )


def mealtime_records(df,meal_name='supper'):
    '''Returns just the records in dataframe df that are in the time interval for meal_name'''
    (meal_start, meal_end) = meal_to_time_range(meal_name)
    print (meal_start,type(meal_start))
    mr = select(df,
                lambda row: (row.date_time.time() >= meal_start and
                             row.date_time.time() <= meal_end))
    
    print 'adding this many mealtime records',len(mr)
    return mr

carbs_and_insulin_together_gap = 10

def carbs_and_insulin_together(df,gap=carbs_and_insulin_together_gap):
    '''returns a dataframe with just the rows for carbs within 'gap' minutes of insulin'''
    results = pandas.DataFrame( columns=df.columns ) # copy of supplied dataframe
    delta = pandas.Timedelta( minutes=gap )
    for a in df.itertuples():
        for b in df.itertuples():
            if a.rec_num >= b.rec_num:
                continue
            if ((b.date_time - a.date_time <= delta) and
                (a.carbs > 0 and b.bolus_volume > 0 or
                 a.bolus_volume > 0 and a.carbs > 0)):
                results = results.append(a._asdict(),ignore_index=True)
                results = results.append(b._asdict(),ignore_index=True)
                print 'len: ',len(results)
    return results

def plausible_basal_amount(ba):
    return ba > 0

def basal_insulin_delta(df_rel, df_meal):
    '''finds a basal_insulin 2 hours prior to meal.

On 8/4, Janice said look 2 hours before the meal; whatever the basal
insulin was then, use that as the pre-meal basal. So for the April 3rd
2016 example day, use 0.2 for the evening meal.
    '''
    global prior_recs, basal_amts
    thirty_mins = datetime.timedelta(hours = 0.5)
    win_start = df_meal.date_time[0] - thirty_mins 
    win_end = df_meal.date_time[len(df_meal)-1] + thirty_mins
    # find earlier basals
    two_hours = datetime.timedelta(hours=2)
    before_meal = df_meal.date_time[0] - two_hours
    df_prior_basals = select(df_rel,
                             lambda row:
                               (not pandas.isnull(row.basal_amt) and
                                not row.basal_amt == 0.0 and
                                row.date_time < before_meal))
    print 'df_prior_basals'
    print df_prior_basals
    if len(df_prior_basals) == 0:
        raise ValueError('figure out how to handle missing data')
    # This is the last value, so the most recent value
    prior = df_prior_basals.basal_amt[len(df_prior_basals)-1]
    print('prior: ',prior)
    # meal basals
    df_meal_basals = select(df_rel,
                           lambda row:
                               (not pandas.isnull(row.basal_amt) and
                                row.basal_amt > prior and
                                row.date_time >= win_start and
                                row.date_time <= win_end))
    print 'df_meal_basals'
    print df_meal_basals
    if len(df_meal_basals) == 0:
        raise ValueError('figure out how to handle missing data')
    meal_basals = df_meal_basals.basal_amt
    meal_basals_max = meal_basals.max()
    meal_basals_min = meal_basals.min()
    if meal_basals_max > meal_basals_min:
        print('ignoring some mealtime basal settings')
    # Find the first record that has the change to meal_basal_max
    df_meal_basals_max = None
    for row in df_meal_basals.itertuples():
        if row.basal_amt == meal_basals_max:
            print('row: ',row)
            df_meal_basals_max = pandas.DataFrame([row._asdict()], columns = df_meal_basals.columns)
            break
    print('df of max basal',df_meal_basals_max)
    meal = df_meal_basals_max.basal_amt[0] # same as meal_basals_max
    change_time = df_meal_basals_max.date_time[0]
    delta = meal - prior
    return ( prior, meal, delta, change_time )

def excess_basal_insulin_post_meal(df,prior_basal, change_time):
    '''returns the sum of basal insulin multiplied by time-interval
for the post-meal period, minus 6*prior_basal. The basal insulin is a rate in units/hour,
right?  This calculation goes for six hours after the meal begins'''
    calcs = []                  # for documentation
    first_time = change_time    # timestamp
    prior_time = df.date_time[0]
    last_time = df.date_time[len(df.date_time)-1]
    print('last timestamp in post-meal rows: ',last_time)
    six_hours = pandas.Timedelta(hours=6)
    end_time = first_time + six_hours
    print('looking until ',end_time)
    if last_time < end_time:
        # since we look until 3am the next day, this shouldn't happen.
        # So, we will assume the last value continues to the end of the 6 hours
        pass
    state = {'curr_basal': prior_basal,
             'curr_time': change_time,
             'running_total': 0,
             'running_time': 0}
    def incr_excess_basal(new_basal, new_time):
        if math.isnan(new_basal):
            new_basal = state['curr_basal']
        td = new_time - state['curr_time'] # a time_delta object
        hrs = td.total_seconds()/(60*60)   # need hrs because basal is in units/hr
        amt = state['curr_basal']*hrs
        state['running_total'] += amt
        state['running_time'] += hrs
        # for explaining this calculation
        calc = ("<p>from {then} to {now} ({hrs}): {curr}*{hrs} = {amt}<p>"
                .format(then=prior_time.strftime("%H:%M"),
                        now=end_time.strftime("%H:%M"),
                        curr=state['curr_basal'],
                        hrs=hrs,
                        amt=amt
                ))
        # print('calc',calc)
        calcs.append(calc)
        # getting ready for next iteration
        state['curr_basal'] = new_basal
        state['curr_time'] = new_time
        
            
    print('looping over ',len(df),' tuples')
    for row in df.itertuples():
        # print('considering row ',row)
        if row.date_time < change_time:
            continue
        if row.date_time > end_time:
            break
        incr_excess_basal(row.basal_amt, row.date_time)
    # after the loop
    if state['running_time'] < 6.0:
        incr_excess_basal(float('nan'),end_time)
    total_excess = state['running_total']-prior_basal*6.0
    calcs.append('<p><strong>sum - 6*base: {total} - {base}*6 = {excess}</strong></p>'
                 .format(total=state['running_total'],
                         base=prior_basal,
                         excess=total_excess))
    print 'total excess: ',total_excess
    return calcs, total_excess

def addstep(sym, val):
    '''add a new step (sym, val) pair, to a dictionary of steps'''
    if sym == 'steps':
        raise ValueError('''Cannot name a step 'steps': %{sym}'''.format(sym=sym))
    if 'steps' not in steps:
        steps['steps'] = []
    steps['steps'].append((sym,val))
    if sym in steps:
        raise ValueError('''You already have a step called %{sym}'''.format(sym=sym))
    steps[sym] = val
    return val

def compute_ic_for_date(date_str, conn=get_db_connection(), steps=dict()):
    global df_all, df_rel, df_meal, meal_carbs, meal_insulin, meal_rec
    global prior_insulin, extra_insulin_calcs, extra_insulin, total_insulin, ic_ratio, meal_span, is_long_meal
    try:
        df_all = get_ic_for_date(date_str, conn=conn)
        if len(df_all) == 0:
            flask.flash('No data for date_str {s}'.format(s=date_str))
            print('No data for date_str {s}'.format(s=date_str))
            util.addstep(steps,'ic_ratio',None)
            return steps
        ## just the relevant data. Add more columns as necessary, but this
        ## makes printing more concise
        df_rel = util.addstep(steps, 'df_rel', df_all[['date_time','basal_amt','bolus_volume','carbs','rec_num']])
        ## first, get the subset of records just for this meal time
        df_mealtime = util.addstep(steps,'mealtime records', mealtime_records(df_rel))
        util.addstep(steps,'df_mealtime',df_mealtime)
        # next, get the initial carbs and insulin, meaning insulin and
        # carbs given within 10 minutes of each other. Return set of rows
        # as a dataframe
        df_meal = carbs_and_insulin_together(df_mealtime)
        if len(df_meal)==0:
            flask.flash('no meals happened for this date and time range')
            print('no meals happened for this date and time range')
            util.addstep(steps,'ic_ratio',None)
            return steps
        meal_time = df_meal.date_time[0]
        util.addstep(steps, 'meal_time', meal_time)
        meal_end = df_meal.date_time[len(df_meal.date_time)-1]
        util.addstep(steps, 'meal_end', meal_end)
        meal_span = meal_end - meal_time
        util.addstep(steps, 'meal_span', meal_span)
        is_long_meal = meal_span > pandas.Timedelta(hours=3)
        util.addstep(steps, 'is_long_meal', is_long_meal)
        ## compute total of carbs and upfront insulin
        meal_carbs = df_meal.carbs.sum()
        util.addstep(steps, 'meal_carbs', meal_carbs)
        meal_insulin = df_meal.bolus_volume.sum()
        util.addstep(steps, 'meal_insulin', meal_insulin)
        print('computing base insulin')
        ## base insulin. Work backwards to find first plausible value prior to meal
        (prior_insulin, meal, delta, change_time) = basal_insulin_delta(df_rel, df_meal)
        print( 'prior_insulin, {p}, changed to {p2} (delta = {d}) at time {t}'
               .format(p=prior_insulin,p2=meal,d=delta,t=change_time))
        util.addstep(steps, 'prior_insulin', prior_insulin)
        util.addstep(steps, 'changed_insulin', meal)
        util.addstep(steps, 'change_time', change_time)  # TO DO. this has the wrong value
        util.addstep(steps, 'change_amount', delta)
        # now, subtract that prior insulin from all insulin subsequent to
        # the meal and sum the excess times the interval
        extra_insulin_calcs, extra_insulin = excess_basal_insulin_post_meal(df_rel, prior_insulin, change_time)
        util.addstep(steps, 'extra_insulin', extra_insulin)
        # compute total insulin as upfront + excess
        initial_insulin = meal_insulin + extra_insulin
        util.addstep(steps, 'initial_insulin', initial_insulin)
        # compute ratio
        initial_ic = meal_carbs / initial_insulin
        print 'Initial I:C ratio is 1:{x}'.format(x=initial_ic)
        util.addstep(steps, 'initial_ic', initial_ic)
        ## effective IC is based on extra boluses given within 6 hours post-meal
        df_post_meal = select_between_times(df_rel,
                                            meal_time,
                                            meal_time+pandas.Timedelta(hours=6))
        correction_insulin = df_post_meal.bolus_volume.sum()
        util.addstep(steps, 'correction_insulin', correction_insulin)
        effective_insulin = initial_insulin+correction_insulin
        util.addstep(steps, 'effective_insulin', effective_insulin)
        util.addstep(steps, 'effective_ic', meal_carbs / effective_insulin )
        print('df_rel as this many records: ',len(df_rel))
        return steps
    except Exception as err:
        print('Got an exception: {err}'.format(err=err))
        return None

def get_cgm_for_date(date_str, conn=get_db_connection(), meal_str='supper'):
    '''returns a pandas.dataframe for the given date and meal. Currently
ignores meal_str, but eventually focus on those records. If the
meal_str doesn't match one of the known values (breakfast, lunch,
supper), returns all records for that date.
    '''
    today = to_date(date_str)
    time = meal_to_time_range(meal_str)
    # I added a clause to get data from the next day, so this will work for supper
    query = ('''select date_time, mgdl from cgm_2 where 
                date(date_time) = '{today}' '''
             .format(today=today.strftime('%Y-%m-%d')))
    print query
    df = pandas.read_sql(query,
                         conn,
                         parse_dates = ['date_time'])
    return df

def get_cgm_for_time_range(start, end, conn=get_db_connection()):
    '''returns a pandas.dataframe for the given time range'''
    # I added a clause to get data from the next day, so this will work for supper
    query = ('''select date_time, mgdl from cgm_2 where 
                date_time >= '{start}' and date_time <= '{end}' '''
             .format(start=start.strftime('%Y-%m-%d %H:%M'),
                     end=end.strftime('%Y-%m-%d %H:%M')))
    print query
    df = pandas.read_sql(query,
                         conn,
                         parse_dates = ['date_time'])
    return df

def compute_excess_bg(df,min_ideal,max_ideal):
    '''Returns the average amount by which the bg exceeds the ideal amount'''
    high_sum = 0
    num_vals = 0
    for cgm in df.mgdl:
        cgm = float(cgm)
        if cgm > max_ideal:
            high_sum += (cgm - max_ideal)
            num_vals += 1
    return high_sum/num_vals

## ================================================================

def format_cgm(df_cgm):
    times = [ ts.isoformat() for ts in df_cgm.date_time.tolist() ]
    vals = [ float(v) for v in df_cgm.mgdl.tolist() ]
    return {'times':times, 'vals':vals}


## ================================================================

def compute_ic_and_excess_bg_for_date(date_str, conn=get_db_connection()):
    print('date_str is a ',type(date_str))
    steps = dict()
    calcs = compute_ic_for_date(date_str, conn, steps)
    if 'meal_time' not in steps:
        meal_time = pandas.Timestamp(str(date_str)+' 18:00') # supper for now
    else:
        meal_time = steps['meal_time']
    meal_time_3 = meal_time+pandas.Timedelta(hours=3)
    meal_time_6 = meal_time+pandas.Timedelta(hours=6)
    df_cgm = get_cgm_for_time_range(meal_time, meal_time_6, conn)
    util.addstep(steps, 'df_cgm', df_cgm)
    df_period1 = select_between_times(df_cgm,
                                      meal_time,
                                      meal_time+pandas.Timedelta(hours=3))
    bg_excess_period1 = compute_excess_bg(df_period1, 80, 120)
    util.addstep(steps, 'bg_excess_period1', bg_excess_period1)
    df_period2 = select_between_times(df_cgm,
                                      meal_time+pandas.Timedelta(hours=3),
                                      meal_time+pandas.Timedelta(hours=6))
    bg_excess_period2 = compute_excess_bg(df_period2, 80, 120)
    util.addstep(steps, 'bg_excess_period2', bg_excess_period2)
    util.addstep(steps, 'cgm_data', format_cgm(df_cgm))
    return steps
    
## ================================================================


def test_calc(date_str='4/3/16'):
    calcs = compute_ic_and_excess_bg_for_date(date_str) 
    return calcs
    
def start_calc(date_str='4/3/16', conn=get_db_connection()):
    global df_all, df_rel, df_meal, meal_carbs, meal_insulin, meal_rec
    global prior_insulin, extra_insulin_calcs, extra_insulin, total_insulin, ic_ratio, meal_span, is_long_meal
    df_all = get_ic_for_date(date_str, conn=conn)
    if len(df_all) == 0:
        flask.flash('No data for date_str {s}'.format(s=date_str))
        print('No data for date_str {s}'.format(s=date_str))
        return [["ic_ratio", None]]
    ## just the relevant data. Add more columns as necessary, but this
    ## makes printing more concise
    df_rel = df_all[['date_time','basal_amt','bolus_volume','carbs','rec_num']]
    ## first, get the subset of records just for this meal time


