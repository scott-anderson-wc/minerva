# This file is a database interface using Pandas dataframes as the
# primary datastructure for sets of records from the database.

import pandas
import MySQLdb
import datetime
import dbconn2
import math
import flask

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
    # It won't work for breakfast or lunch because of the time cut-off.
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

def base_insulin_delta(df_rel, df_meal):
    '''find a change to the base_insulin within +/- 30 minutes of df_meal. 

This algorith finds a plausible (non-zero) base_insulin amount more
than 1 hour before the meal such that there was an increase to that
base amount during a 30 minute window around the meal.  Returns a
tuple of the base amount, the changed amount, and the delta (second
minus first)
    '''
    global prior_recs, basal_amts
    thirty_mins = datetime.timedelta(hours = 0.5)
    win_start = df_meal.date_time[0] - thirty_mins 
    win_end = df_meal.date_time[len(df_meal)-1] + thirty_mins
    df_meal_basal = select(df_rel,
                           lambda row:
                               (not pandas.isnull(row.basal_amt) and
                                row.date_time >= win_start and
                                row.date_time <= win_end))
    print 'changes to basal during meal hour window',df_meal_basal
    # find earlier basals
    hour = datetime.timedelta(hours=1)
    before_meal = df_meal.date_time[0] - hour
    df_prior_basals = select(df_rel,
                             lambda row:
                               (not pandas.isnull(row.basal_amt) and
                                not row.basal_amt == 0.0 and
                                row.date_time < before_meal))
    print 'prior basal values',df_prior_basals
    if len(df_meal_basal) == 0:
        raise ValueError('figure out how to handle missing data')
    if len(df_prior_basals) == 0:
        raise ValueError('figure out how to handle missing data')
    prior = df_prior_basals.basal_amt[len(df_prior_basals)-1]
    meal_basals = df_meal_basal.basal_amt
    meal_basals_max = meal_basals.max()
    meal_basals_min = meal_basals.min()
    if meal_basals_max > meal_basals_min:
        raise ValueError('too many different meal_basal values')
    meal = df_meal_basals.basal_amt[0]
    change_time = df_meal_basals.date_time
    delta = meal - prior
    return ( prior, meal, delta, change_time )

def excess_basal_insulin_post_meal(df,prior_basal, change_time):
    '''returns the sum of basal insulin multiplied by time-interval
for the post-meal period, minus 6*prior_basal. The basal insulin is a rate in units/hour,
right?  This calculation goes for six hours after the meal begins'''
    calcs = []                  # for documentation
    first_time = change_time
    prior_time = df.date_time[0]
    last_time = df.date_time[len(df.date_time)-1]
    six_hours = pandas.Timedelta(hours=6)
    end_time = first_time + six_hours
    curr_basal = prior_basal
    if last_time < end_time:
        raise ValueError('Did not have 6 hours of data')
    running_total = 0
    running_time_total = 0
    for row in df.itertuples():
        if row.date_time < change_time:
            continue
        if row.date_time > end_time:
            if prior_time < end_time and curr_basal > prior_basal:
                # add the last little bit
                td = end_time - prior_time
                hrs = td.total_seconds()/(60*60)
                running_time_total += hrs
                amt = curr_basal * hrs
                calc = ("<p>from {then} to {now} ({hrs}): {curr}*{hrs} = {amt}<p>"
                        .format(then=prior_time.strftime("%H:%M"),
                                now=end_time.strftime("%H:%M"),
                                curr=curr_basal,
                                hrs=hrs,
                                amt=amt
                        ))
                calcs.append(calc)
                running_total += amt
            break
        if (not math.isnan(row.basal_amt) and
            row.basal_amt > prior_basal):
            td = (row.date_time - prior_time) # a pandas Timedelta object
            hrs = td.total_seconds()/(60*60)
            running_time_total += hrs
            amt = curr_basal * hrs
            calc = ("<p>from {then} to {now} ({hrs}): {curr}*{hrs} = {amt}<p>"
                    .format(then=prior_time.strftime("%H:%M"),
                            now=row.date_time.strftime("%H:%M"),
                            curr=curr_basal,
                            hrs=hrs,
                            amt=amt
                    ))
            calcs.append(calc)
            running_total += amt
            prior_time = row.date_time # new prior time
            curr_basal = row.basal_amt
    # after the loop
    if running_time_total != 6.0:
        print 'error: time does not total to 6 hours: {tot}'.format(tot=running_time_total)
        raise ValueError('incorrect time total')
    total_excess = running_total-prior_basal*6.0
    calcs.append('<p><strong>sum - 6*base: {total} - {base}*6 = {excess}</strong></p>'
                 .format(total=running_total,
                         base=prior_basal,
                         excess=total_excess))
    print 'total excess: ',total_excess
    return calcs, total_excess

def compute_ic_for_date_old(date_str, conn=get_db_connection()):
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
    df_mealtime = mealtime_records(df_rel)
    # next, get the initial carbs and insulin, meaning insulin and
    # carbs given within 10 minutes of each other. Return set of rows
    # as a dataframe
    df_meal = carbs_and_insulin_together(df_mealtime)
    if len(df_meal)==0:
        flask.flash('no meals happened for this date and time range')
        print('no meals happened for this date and time range')
        return [["df_rel", df_rel],
                ["ic_ratio", None]]
    meal_time = df_meal.date_time[0]
    meal_end = df_meal.date_time[len(df_meal.date_time)-1]
    meal_span = meal_end - meal_time
    is_long_meal = meal_span > pandas.Timedelta(hours=3)
    ## compute total of carbs and upfront insulin
    meal_carbs = df_meal.carbs.sum()
    meal_insulin = df_meal.bolus_volume.sum()
    ## base insulin. Work backwards to find first plausible value prior to meal
    (prior_insulin, meal, delta, change_time) = base_insulin_delta(df_rel, df_meal)
    print( 'prior_insulin, %{p}, changed to {p2} (delta = {d}) at time {t}'
           .format(p=prior_insulin,p2=meal,d=delta,t=change_time))
    # now, subtract that prior insulin from all insulin subsequent to
    # the meal and sum the excess times the interval
    extra_insulin_calcs, extra_insulin = excess_basal_insulin_post_meal(df_rel, prior_insulin, change_time)
    # compute total insulin as upfront + excess
    total_insulin = meal_insulin + extra_insulin
    # compute ratio
    ic_ratio = meal_carbs / total_insulin
    print 'I:C ratio is 1:{x}'.format(x=ic_ratio)
    return [['df_rel', df_rel],
            ['df_meal', df_meal],
            ['meal_time', meal_time],
            ['meal_span', meal_span],
            ['is_long_meal', is_long_meal],
            ['meal_carbs', meal_carbs],
            ['meal_insulin', meal_insulin],
            ['meal_rec', meal_rec],
            ['prior_insulin', prior_insulin],
            ['extra_insulin_calcs', extra_insulin_calcs],
            ['extra_insulin', extra_insulin],
            ['total_insulin', total_insulin],
            ['ic_ratio', ic_ratio]]
    
            


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

def compute_ic_for_date(date_str, conn=get_db_connection()):
    global df_all, df_rel, df_meal, meal_carbs, meal_insulin, meal_rec
    global prior_insulin, extra_insulin_calcs, extra_insulin, total_insulin, ic_ratio, meal_span, is_long_meal
    try:
        steps = dict()
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

        meal_insulin = df_meal.bolus_volume.sum()
        print('computing base insulin')
        ## base insulin. Work backwards to find first plausible value prior to meal
        (prior_insulin, meal, delta, change_time) = base_insulin_delta(df_rel, df_meal)
        print( 'prior_insulin, {p}, changed to {p2} (delta = {d}) at time {t}'
               .format(p=prior_insulin,p2=meal,d=delta,t=change_time))
        # now, subtract that prior insulin from all insulin subsequent to
        # the meal and sum the excess times the interval
        extra_insulin_calcs, extra_insulin = excess_basal_insulin_post_meal(df_rel, prior_insulin, change_time)
        # compute total insulin as upfront + excess
        total_insulin = meal_insulin + extra_insulin
        # compute ratio
        ic_ratio = meal_carbs / total_insulin
        print 'I:C ratio is 1:{x}'.format(x=ic_ratio)
        return [['df_rel', df_rel],
                ['df_meal', df_meal],
                ['meal_time', meal_time],
                ['meal_span', meal_span],
                ['is_long_meal', is_long_meal],
                ['meal_carbs', meal_carbs],
                ['meal_insulin', meal_insulin],
                ['meal_rec', meal_rec],
                ['prior_insulin', prior_insulin],
                ['extra_insulin_calcs', extra_insulin_calcs],
                ['extra_insulin', extra_insulin],
                ['total_insulin', total_insulin],
                ['ic_ratio', ic_ratio]]
    except Exception as err:
        print('Got an exception: {err}'.format(err=err))
        return None

def test_calc(date_str='4/3/16'):
    return compute_ic_for_date(date_str)
    
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


