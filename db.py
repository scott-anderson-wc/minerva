# Python module to act as our database interface
import MySQLdb
import dbconn2
from datetime import datetime, timedelta

import json
import plotly
import plotly.plotly as py
import plotly.graph_objs as go
import pprint

# Should put these in a config file

dt_format = '%Y%m%d%H%M'        # the format for date_time in the database, for datetime.strptime()

def debug(*args):
    s = ' '.join(map(str,args))
    if app.debug:
        print("debug: "+s)
    else:
        app.logger.debug(s)

def dictCursor():
    dsn = dbconn2.read_cnf('/home/hugh9/.my.cnf')
    conn = dbconn2.connect(dsn)
    curs = conn.cursor(MySQLdb.cursors.DictCursor)
    return curs

def cgm_data_range(curs=dictCursor()):
    curs.execute('''select min(date_time) as a, max(date_time) as b from cgm_2''')
    row = curs.fetchone()
    return (row['a'], row['b'])

def insulin_carb_data_range(curs=dictCursor()):
    curs.execute('''select min(date_time) as a, max(date_time) as b from insulin_carb_2''')
    row = curs.fetchone()
    return (row['a'], row['b'])


def makeTableRowHTML(cols, row):
    cells = [ '<td>{d}</td>'.format(d=row[c]) for c in cols ]
    cells.insert(0,'<tr>')
    cells.append('</tr>\n')
    return ''.join(cells)

def makeTableHTML(cols,data):
    headers = [ '<th>{c}</th>'.format(c=c) for c in cols]
    rows = [ makeTableRowHTML(cols,row) for row in data ]
    return ('<table class="bordered">\n'+
            ''.join(headers)+'\n'+
            ''.join(rows)+
            '</table>')

def whoami(curs):
    curs.execute('''SELECT user() as u''')
    d = curs.fetchone()
    return d['u']

def dateRange(curs,table):
    curs.execute('''SELECT min(date_time) as min, max(date_time) AS max
FROM {table}'''.format(table=table))
    return curs.fetchone() # there's only one row, but it'll be a dictionary


def remove_empty_cols(cols,records):
    empty = []
    for c in cols:
        if all(rec[c] == '' for rec in records):
            empty.append(c)
    for e in empty:
        cols.remove(e)

def col(records,col_name):
    return [ r[col_name] for r in records ]

def rec_nums(records):
    return [ str(r) for r in col(records,'rec_num') ]

def findMeals(data, timediff=timedelta(minutes=10)):
    '''Adds a column called meal when carbs&insulin are within 10 minutes of each other
    If there's another meal within 1 hour, counts that as the same meal. Labels the meals as meal_1, etc in a  new column called 'meal'.  Then, adds 'breakfast' for a meal before 10am, lunch for a meal between 10am and 4pm and dinner for anything after 4pm. '''
    global log, meal_data, groups, pairs, ic_initial
    log = []
    # remove data other than insulin_bolus and carbs
    meal_data = [ d for d in data
                  if (d['bolus_volume'] > 0 or
                      d['carbs'] > 0 ) ]
    # msg = ('Found {n} possible meal records {recs}'.format(n=len(meal_data),
    #                                                        recs=','.join(rec_nums(meal_data))))
    # print msg
    # log.append(msg)
    groups = []
    for d1 in meal_data:
        # note that this will not catch itself because the rec_num has to be higher
        others = [ d for d in meal_data
                   if ( d['rec_num'] > d1['rec_num'] and
                        abs(d['date_time'] - d1['date_time']) >= timedelta(0) and
                        abs(d['date_time'] - d1['date_time']) < timediff) ]
        others.insert(0,d1)
        # msg = ('Found group of {n} records as one meal {recs}'.format(n=len(others),
        #                                                               recs=','.join(rec_nums(others))))
        # print msg
        # log.append(msg)
        if len(others) > 0:
            groups.append(others)
    for g in groups:
        if len(g) > 2:
            msg = 'Found group of >2 records; skipping'
            debug(msg)
            log.append(msg)
    for g in groups:
        if len(g) < 2:
            # msg = 'Found group of <2 records; skipping'
            # print msg
            # log.append(msg)
            pass
    pairs = [ g for g in groups if len(g) == 2 ]
    ic_initial = []
    for p in pairs:
        a = p[0]
        b = p[1]
        carbs = max(a['carbs'], b['carbs'])
        bolus = max(a['bolus_volume'], b['bolus_volume'])
        msg = ('meal match with carbs = {c} and bolus = {b} using records {recs}'.format(
                c=carbs,b=bolus,recs=','.join(rec_nums(p))))
        debug(msg)
        log.append(msg)
        # dc is the combo
        dc = dict( date = a['date_time'], # guaranteed to be the min
                   time = a['date_time'].isoformat(),
                   when = a['date_time'].strftime('%H:%M'),
                   carbs = carbs,
                   bolus = bolus,
                   ratio_float = carbs/bolus,
                   ratio = '%2f'%(carbs/bolus),
                   basis = rec_nums(p))
        debug('dc',dc)
        ic_initial.append(dc)
    debug('Found ',len(ic_initial))
    return ic_initial

def getICByDateRaw(datestr,curs=dictCursor()):
    global daydata
    try:
        datetime.strptime(datestr,'%Y%m%d')
    except ValueError:
        debug('invalid datestr in getICByDateRaw: ',datestr)
        return
    debug('looking up IC by date {d}'.format(d=datestr))
    curs.execute('''SELECT *
FROM insulin_carb_2
WHERE date(date_time) = %(date)s''',
                 {'date':datestr})
    data = curs.fetchall()
    return data

def getICByDate(date,curs=dictCursor()):
    global daydata
    debug('looking up IC by date {d}'.format(d=datestr(date)))
    curs.execute('''SELECT *
FROM insulin_carb_2
WHERE date(date_time) = %(date)s''',
                 {'date': datestr(date)})
    daydata = curs.fetchall()
    debug('got this many rows:', len(daydata))
    for d in daydata:
        # no longer needed, since date_time is a datetime datatype
        # d['date_time'] = datetime.strptime(d['date_time'], dt_format)
        if d['carbs'] != '':
            d['carbs'] = float(d['carbs'])
        else:
            d['carbs'] = 0.0
        if d['bolus_volume'] != '':
            d['bolus_volume'] = float(d['bolus_volume'])
        else:
            d['bolus_volume'] = 0.0
    return findMeals(daydata)

def getICRatioByDate(date,curs=dictCursor()):
    pass

def getEffectiveICRatioByDate(date,curs=dictCursor()):
    pass

def test(datestr='2016-08-24'):
    debug('testing with '+datestr)
    d = datetime.strptime(datestr)
    return getICByDate(d)
    
# ================================================================

def getCGMByDate(date,curs=dictCursor()):
    '''date should be a date object'''
    debug('looking up CGM by date {d} ({s})'.format(d=date,s=datetime.strftime(date,'%Y-%m-%d')))
    curs.execute('''SELECT date_time, mgdl FROM cgm_2
WHERE date(date_time) = %(date)s''',
                 {'date': datestr(date)})
    cgm = curs.fetchall()
    debug('got this many cgm rows:', len(cgm))
    for d in cgm:
        # no longer needed
        # d['date_time'] = datetime.strptime(d['date_time'], dt_format)
        d['mgdl'] = float(d['mgdl'])
    return cgm

    
def datestr(date):
    '''returns a date string for searching the database'''
    return datetime.strftime(date,'%Y-%m-%d')

def datestr_and_timestr(datestr,timestr):
    return datetime.strptime(datestr+timestr,'%Y-%m-%d%H:%M')

def strip_hyphens(s):
    return ''.join(s.split('-'))

def plotCGMByDate(date, curs=dictCursor()):
    global cgm, times, vals, trace, data, layout, graph, graphJSON
    cgm = getCGMByDate(date)
    # times = [ r['date_time'].strftime('%H:%M') for r in cgm ]
    times = [ r['date_time'].isoformat() for r in cgm ]
    vals = [ r['mgdl'] for r in cgm ]
    if len(cgm) == 0:
        return None
    trace = go.Scatter(x = times,
                       y = vals,
                       name = 'cgm')
    # mealtimes = [ datestr_and_timestr(datestr,t).isoformat() for t in ['13:28','13:54','19:10','20:10']]
    data = [trace]
    layout = go.Layout(title='CGM for '+datestr(date),
                       xaxis = dict(title = 'time of day'),
                       yaxis = dict(title = 'mg per dl', autotick=True)
                       )
    graph = go.Figure(data = data, layout = layout)
    # with open('plot1.py','w') as f:
    #     json.dump(dict(times=times,vals=vals,
    #                    meals=meals,
    #                    ratios=[14.05,16.00,18.69,10.00]),
    #               f)
    graphJSON = json.dumps( graph, cls=plotly.utils.PlotlyJSONEncoder)
    return dict( data=data,
                 layout=layout,
                 graph=graph,
                 graphJSON=graphJSON)

                
