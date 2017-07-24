import pandas
import MySQLdb
import re
import datetime
import dbconn2
import math

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

db_connection = None

def get_db_connection():
    global db_connection
    if db_connection:
        return db_connection
    else:
        dsn = dbconn2.read_cnf('/home/hugh9/.my.cnf')
        db_connection = dbconn2.connect(dsn)
        return db_connection

def meal_to_time_range(meal_str):
    '''return a SQL query restricting records for just one meal.'''
    # this definition doesn't leave any time range out
    if meal_str == 'breakfast':
        return '''time(date_time) < '10:00' '''
    elif meal_str == 'lunch':
        return '''time(date_time) >= '10:00' time(date_time) < '16:00' '''
    elif meal_str == 'supper':
        return '''time(date_time) >= '16:00' '''
    else:
        return 'true'

def get_ic_for_date(date_str, meal_str='supper'):
    '''returns a pandas.dataframe for the given date and meal. If the
meal_str doesn't match one of the known values (breakfast, lunch,
supper), returns all records for that date.'''
    conn = get_db_connection()
    date = to_date(date_str)
    time = meal_to_time_range(meal_str)
    query = ('''select * from insulin_carb_2 where date(date_time) = '{date}' and {time}'''
             .format(date=date.strftime('%Y-%m-%d'),
                     time=time))
    print query
    df = pandas.read_sql(query,
                         conn,
                         parse_dates = ['date_time'])
    return df

carbs_and_insulin_meal_gap = 10

def floaty(str):
    if str=='':
        return 0.0
    else:
        return float(str)

tups = []

def carbs_and_insulin_within_meal_gap(df,gap=carbs_and_insulin_meal_gap):
    '''returns a dataframe with just the rows for carbs within 'gap' minutes of insulin'''
    results = pandas.DataFrame( columns=df.columns )
    delta = pandas.Timedelta( minutes=gap )
    global tups
    for a in df.itertuples():
        for b in df.itertuples():
            if a.rec_num >= b.rec_num:
                continue
            if ((b.date_time - a.date_time <= delta) and
                (floaty(a.carbs) > 0 and floaty(b.bolus_volume) > 0 or
                 floaty(a.bolus_volume) > 0 and floaty(a.carbs) > 0)):
                print a.rec_num, b.rec_num
                tups.append(a)
                tups.append(b)
                results = results.append(a._asdict(),ignore_index=True)
                results = results.append(b._asdict(),ignore_index=True)
                print 'len: ',len(results)
    return results

def plausible_basal_amount(ba):
    return ba > 0

def prior_base_insulin(df, meal_rec_num):
    '''find basal_amt previous to meal_rec_num. Has to be plausible.'''
    global prior_recs, basal_amts
    prior_recs = df.query('rec_num < '+str(meal_rec_num))
    if len(prior_recs) == 0:
        raise ValueError('No records prior to meal!')
    # reverse their order
    prior_recs.reindex(index=prior_recs.index[::-1])
    basal_amts = prior_recs.basal_amt
    for ba in basal_amts:
        if plausible_basal_amount(ba):
            return ba

def excess_basal_insulin_post_meal(df,prior_basal):
    '''returns the sum of excess basal insulin multiplied by time-interval
for the post-meal period. The basal insulin is a rate in units/hour,
right?  This calculation only goes until the end of the meal period
(midnight for supper, etc.)
    '''
    calcs = []                  # for documentation
    prior_time = df.date_time[0]
    running_total = 0
    for row in df.itertuples():
        if (not math.isnan(row.basal_amt) and
            row.basal_amt > prior_basal):
            td = (row.date_time - prior_time) # a pandas Timedelta object
            excess = row.basal_amt - prior_basal
            hrs = td.total_seconds()/(60*60)
            amt = excess * hrs
            calc = ("({curr} - {base})*{time} = {excess}*{hrs} = {amt}"
                    .format(curr=row.basal_amt,
                            base=prior_basal,
                            time=td,
                            excess=excess,
                            hrs=hrs,
                            amt=amt
                    ))
            calcs.append(calc)
            running_total += amt
            prior_time = row.date_time # new prior time
    print 'total excess: ',running_total
    return calcs, running_total

def compute_ic_for_date(date_str):
    global df_all, df_rel, df_meal, meal_carbs, meal_insulin, meal_rec, prior_insulin, extra_insulin_calcs, extra_insulin, total_insulin, ic_ratio
    df_all = get_ic_for_date(date_str)
    ## just the relevant data. Add more columns as necessary, but this
    ## makes printing more concise
    df_rel = df_all[['date_time','basal_amt','bolus_volume','carbs','rec_num']]
    # first, get the initial carbs and insulin, meaning insulin and
    # carbs given within 10 minutes of each other. Return set of rows
    # as a dataframe
    df_meal = carbs_and_insulin_within_meal_gap(df_rel)
    ## compute total of carbs and upfront insulin
    meal_carbs = df_meal.carbs.sum()
    meal_insulin = df_meal.bolus_volume.sum()
    ## base insulin. Work backwards to find first plausible value prior to meal
    meal_rec = df_meal.rec_num[0]
    prior_insulin = prior_base_insulin(df_rel, meal_rec)
    print 'prior_insulin', prior_insulin
    # now, subtract that prior insulin from all insulin subsequent to
    # the meal and sum the excess times the interval
    extra_insulin_calcs, extra_insulin = excess_basal_insulin_post_meal(df_rel, prior_insulin)
    # compute total insulin as upfront + excess
    total_insulin = meal_insulin + extra_insulin
    # compute ratio
    ic_ratio = meal_carbs / total_insulin
    print 'I:C ratio is 1:{x}'.format(x=ic_ratio)
    return {'df_rel': df_rel,
            'df_meal': df_meal,
            'meal_carbs': meal_carbs,
            'meal_insulin': meal_insulin,
            'meal_rec': meal_rec,
            'prior_insulin': prior_insulin,
            'extra_insulin_calcs': extra_insulin_calcs,
            'extra_insulin': extra_insulin,
            'total_insulin': total_insulin,
            'ic_ratio': ic_ratio}
    
def test_calc(datestr='4/3/16'):
    return compute_ic_for_date(datestr)
    
