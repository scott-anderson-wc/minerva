import sys
import re
import dbi
import MySQLdb
import datetime

def make_date(date_or_date_str):
    '''returns a date object, given either a date/datetime object or a string in MySQL syntax'''
    d = date_or_date_str
    if type(d) == datetime.date:
        return d
    if type(d) == datetime.datetime:
        return d.date()
    if type(d) == str:
        return datetime.datetime.strptime(d,'%Y-%m-%d')

def time_str(date):
    '''converts a Python datetime to a readable string, like HH:MM'''
    return date.strftime("%H:%M")

def mysql_date_str(date):
    # print('in mysql_date_str, date is {} ({})'.format(date,type(date)))
    val = make_date(date).strftime('%Y-%m-%d')
    # print('{} => {}'.format(date,val))
    return val

def print_dates(date_seq):
    '''Prints a sequence of date objects in US format'''
    for d in date_seq:
        d = make_date(d)
        print(d.strftime('%m/%d/%Y'))

def get_meal_dates(conn, date1, date2, meal_kind,
                   food_items_include, food_items_exclude):
    '''return a list of meal_dates between date1 and date2 (both either
datetime objects or strings in MySQL syntax) where the meal_kind is
breakfast/lunch/dinner and the meal contains all the items in the
food_items_include list and none of the excluded ones.

    '''
    date1 = make_date(date1)
    date2 = make_date(date2)
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
    print(dates)
    print_dates(dates)
    return dates

def all_dates(conn, date1, date2, meal_kind):
    '''returns a list of all dates in the date range for which we have
info about the given meal_kind.'''
    date1 = make_date(date1)
    date2 = make_date(date2)
    curs = conn.cursor()
    curs.execute('''SELECT date FROM food_diary_2 
                    WHERE date BETWEEN cast(%s as date) and cast(%s as date)
                    AND meal = %s''',
                 [date1, date2, meal_kind])
    rows = curs.fetchall()
    dates = [make_date(row[0]) for row in rows]
    return dates

def get_complement_dates(conn, date1, date2, meal_kind, date_list):
    '''Returns a list of dates between date1 and date2 of meal_kind where
the dates are *not* in the date_list. Return type is date object
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
    # the call to make_date is probably unnecessary, since MySQLdb does this
    # but it doesn't hurt and makes sure that they are date objects.
    dates = [make_date(row[0]) for row in rows]
    return dates

if __name__ == '__main__':
    if len(sys.argv) == 1:
        print('usage: script date1 date2 meal_kind include_food_item...')
        print('''try: script '2016-04-02' '2016-05-03' dinner avocado ''')
        sys.exit()
    conn = dbi.get_conn()

    date1,date2,meal = sys.argv[1:4]
    date1 = make_date(date1)
    date2 = make_date(date2)

    ## the between operator is <= on both sides
    group0 = all_dates(conn,date1,date2,meal)
    print(group0)
    print('all dates in food_diary_2 in that range with that meal')
    print_dates(group0)

    # the function handles two lists, possibly empty. Let's try all five possibilities up to length 2
    group1 = get_meal_dates(conn, date1, date2, meal, [], [])
    group1 = get_meal_dates(conn, date1, date2, meal, ['avocado'], [])
    group1 = get_meal_dates(conn, date1, date2, meal, ['avocado','pasta'], [])
    group1 = get_meal_dates(conn, date1, date2, meal, ['avocado'], ['bean'])
    group1 = get_meal_dates(conn, date1, date2, meal, ['avocado','pasta'], ['bean','rice'])

    print('group1 dates: meals with avocado and pasta and without beans and without rice')
    print_dates(group1)

    group2 = get_complement_dates(conn, date1, date2, meal, group1)
    print('complement dates')
    print_dates(group2)
