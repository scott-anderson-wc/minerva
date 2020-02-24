import sys
import re
import dbi
import MySQLdb
import datetime

def us_date(mysql_date):
    '''converts a MySQL date string %Y-%m-%d to a US string %m/%d/%Y'''
    d = datetime.datetime.strptime(mysql_date, '%Y-%m-%d')
    return d.strftime('%m/%d/%Y')

def time_str(date):
    '''converts a Python datetime to a readable string, like HH:MM'''
    return date.strftime("%H:%M")

def us_date_wo_padding(mysql_date):
    '''converts a MySQL date string %Y-%m-%d to a US string %m/%d/%Y but
without the zero padding that is standard. Don't use this except when querying 
the varchar tables.
    '''
    d = datetime.datetime.strptime(mysql_date, '%Y-%m-%d')
    d2 = d.date()
    return '{}/{}/{}'.format(d2.month,d2.day,d2.year)

def mysql_date_str(date):
    # print('in mysql_date_str, date is {} ({})'.format(date,type(date)))
    val = date.strftime('%Y-%m-%d')
    # print('{} => {}'.format(date,val))
    return val

def print_dates(date_seq):
    for d in date_seq:
        if type(d) is str:
            d = datetime.datetime.strptime(d, '%Y-%m-%d')
        print(d.strftime('%m/%d/%Y'))

def get_meal_dates_with(conn, date1, date2, meal_kind, *food_items):
    '''return a list of meal_dates between date1 and date2 
where the meal contained one of the items in the food_items list'''
    # we will eliminate duplicates from this list. We could consider
    # using a hash if we expect many dates and many duplicates, but
    # that seems unlikely
    dates = []
    curs = conn.cursor()
    args = [date1, date2, meal_kind]
    for fi in food_items:
        fi_pat = '%'+fi+'%'
        fi9 = [fi_pat] * 9
        print(args+fi9)
        curs.execute('''SELECT date FROM food_diary_2
                        WHERE date BETWEEN cast(%s as date) and cast(%s as date)
                        AND meal = %s
                        AND (item1 like %s or
                             item2 like %s or
                             item3 like %s or
                             item4 like %s or
                             item5 like %s or
                             item6 like %s or
                             item7 like %s or
                             item8 like %s or
                             item9 like %s)''',
                     args + fi9)
        # append w/o duplicates
        for row in curs.fetchall():
            d = row[0]
            if d not in dates:
                dates.append(d)
    return dates

def isDateStr(dateStr):
    try:
        d = datetime.datetime.strptime(dateStr,'%Y-%m-%d')
        return True
    except:
        return False

def get_meal_dates_with_better(conn, date1, date2, meal_kind,
                               food_items_include, food_items_exclude):
    '''return a list of meal_dates between date1 and date2 where the meal
contains all the items in the food_items_include list and none
of the excluded ones.
    '''
    if not isDateStr(date1):
        raise TypeError('not a date string: {}'.format(date1))
    if not isDateStr(date2):
        raise TypeError('not a date string: {}'.format(date2))
    if meal_kind not in ['breakfast','lunch','dinner']:
        raise ValueError('not a meal kind')
    
    def meal_includes_clause(item):
        '''This should use a regexp to check that the item only contains letters and spaces'''
        item = '%'+item.lower()+'%'
        items = [item] * 9
        return '''(item1 like '{}' or
                   item2 like '{}' or
                   item3 like '{}' or
                   item4 like '{}' or
                   item5 like '{}' or
                   item6 like '{}' or
                   item7 like '{}' or
                   item8 like '{}' or
                   item9 like '{}')'''.format(*items)
    in_clause = ' True '
    if len(food_items_include) > 0:
        in_clause = ' and '.join([ meal_includes_clause(item)
                                   for item in food_items_include])
    # print('in_clause '+in_clause)
    out_clause = ' False '
    if len(food_items_exclude) > 0:
        out_clause = ' and not '.join([ meal_includes_clause(item)
                                        for item in food_items_exclude])
    
    # print('out_clause '+out_clause)
    stmt = '''SELECT date FROM food_diary_2
              WHERE date BETWEEN cast('{}' as date) and cast('{}' as date)
              AND meal = '{}' AND {} AND NOT {}
           '''.format(date1,date2,meal_kind,in_clause,out_clause)
    # print('stmt '+stmt)
    curs = conn.cursor()
    curs.execute(stmt)
    # I don't think duplicates are possible, so we'll skip that.
    dates = [ row[0] for row in curs.fetchall() ]
    print('found {} meals with {} and excluding {}'
          .format(len(dates),food_items_include,food_items_exclude))
    print_dates(dates)
    return dates

def all_dates(conn, date1, date2, meal_kind):
    '''returns a list of all dates in the date range for which we have
info about the given meal_kind.'''
    curs = conn.cursor()
    curs.execute('''SELECT date FROM food_diary_2 
                    WHERE date BETWEEN cast(%s as date) and cast(%s as date)
                    AND meal = %s''',
                 [date1, date2, meal_kind])
    rows = curs.fetchall()
    dates = [row[0] for row in rows]
    return dates

def get_complement_dates(conn, date1, date2, meal_kind, date_list):
    '''Returns a list of dates between date1 and date2 of meal_kind where
the dates are *not* in the date_list
    '''
    ## do the complement by string construction. Ick. Since they are known to be
    ## date objects, this is safe
    ## wrapping the string quotes is necessary
    dates_str_with = ','.join(["'{}'".format(mysql_date_str(d)) for d in date_list])
    print('dates to exclude: '+dates_str_with)
    curs = conn.cursor()

    query = '''SELECT date FROM food_diary_2 
               WHERE date BETWEEN cast(%s as date) and cast(%s as date)
               AND meal = %s
               AND date NOT IN ({})'''.format(dates_str_with)
    # print('complement date sql',query)
    curs.execute(query, [date1, date2, meal_kind])
    rows = curs.fetchall()
    dates = [mysql_date_str(row[0]) for row in rows]
    return dates

def get_meal_dates_without(conn, date1, date2, meal_kind, *food_items):
    '''return a list of meal_dates between date1 and date2 
where the meal did not contain any of the items in the food_items list'''
    # we will eliminate duplicates from this list. We could consider
    # using a hash if we expect many dates and many duplicates, but
    # that seems unlikely
    dates_with = get_meal_dates_with(conn, date1, date2, meal_kind, *food_items)
    ## do the complement by string construction. Ick. Since they are known to be
    ## date objects, this is safe
    dates_str_with = ','.join([mysql_date_str(d) for d in dates_with])
    print('dates to exclude: '+dates_str_with)
    curs = conn.cursor()

    curs.execute('''SELECT date FROM food_diary_2 
                    WHERE date BETWEEN cast(%s as date) and cast(%s as date)
                    AND meal = %s
                    AND date NOT IN ({})'''.format(dates_str_with),
                 [date1, date2, meal_kind])
    rows = curs.fetchall()
    dates = [mysql_date_str(row[0]) for row in rows]
    return dates

def get_cgm_post_meal(conn, date, meal_kind, duration):
    '''return a list of CGM values from insulin_carb_smoothed_2 for
`duration` minutes after `meal` on `date`
    '''
    curs = conn.cursor()
    curs.execute('''select rtime from insulin_carb_smoothed_2 
                    where date(rtime) = %s and carb_code = %s''',
                 [date, meal_kind])
    rows = curs.fetchall()
    if len(rows) == 0:
        print('no such {} on {}'.format(meal,date))
        return []
    if len(rows) > 1:
        print('There are {} {} for {}'.format(len(rows),meal,date))
        print([ time_str(row[0]) for row in rows ])
        print('using '+time_str(rows[-1][0]))
    ## normal/multiple case, take the last row
    meal_start = rows[-1][0]
    print('meal start at {} '.format(meal_start))
    ## Now, get the cgm values
    curs.execute('''select cgm from insulin_carb_smoothed_2
                    where date(rtime) = %s 
                      and rtime >= %s 
                      and minutes_since_last_meal <= %s''',
                 [date, meal_start, duration])
    ## return cgm values
    cgm_values = [ row[0] for row in curs.fetchall()]
    print('for {} found {} cgm values'.format(date,len(cgm_values)))
    return cgm_values

if __name__ == '__main__':
    if len(sys.argv) == 1:
        print('usage: script date1 date2 meal_kind include_food_item...')
        print('''try: script '2016-04-02' '2016-05-03' dinner avocado ''')
        sys.exit()
    conn = dbi.get_conn()

    date1,date2,meal = sys.argv[1:4]
    print('us dates: {} to {}'.format(us_date_wo_padding(date1),us_date_wo_padding(date2)))

    ## the between operator is <= on both sides
    group0 = all_dates(conn,date1,date2,meal)
    print('all dates in food_diary_2 in that range with that meal')
    print_dates(group0)

    # the function handles two lists, possibly empty. Let's try all five possibilities up to length 2
    group1 = get_meal_dates_with_better(conn, date1, date2, meal, [], [])
    group1 = get_meal_dates_with_better(conn, date1, date2, meal, ['avocado'], [])
    group1 = get_meal_dates_with_better(conn, date1, date2, meal, ['avocado','pasta'], [])
    group1 = get_meal_dates_with_better(conn, date1, date2, meal, ['avocado'], ['bean'])
    group1 = get_meal_dates_with_better(conn, date1, date2, meal, ['avocado','pasta'], ['bean','rice'])

    print('group1 dates: meals with avocado and pasta and without beans and without rice')
    print_dates(group1)

    group2 = get_complement_dates(conn, date1, date2, meal, group1)
    print('complement dates')
    print_dates(group2)

    # older test code
    sys.exit()
    cgm_days = [ get_cgm_post_meal(conn, date, meal, 3*60) for date in group1 ]
    for lst in cgm_days:
        print(len(lst))
    # now, print all the data
    print(cgm_days)
