import os
from flask import (Flask, render_template, make_response, request, redirect, url_for,
                   session, flash, send_from_directory, g)
from flask import jsonify
from werkzeug import secure_filename

import time
import logging
import random
import math

LOGFILE='app.log'
LOGLEVEL=logging.DEBUG

from logging.handlers import RotatingFileHandler

from flask_mysqldb import MySQL
from datetime import datetime, timedelta
import db
import pandb
from dbi import get_dsn, get_conn # connect to the database
import isf2 as isf
import date_ui

import json
import plotly
import plotly.plotly as py
import plotly.graph_objs as go

import util

import builtins

def debug(*args):
    s = ' '.join(map(str,args))
    if app.debug:
        print(("debug: "+s))
    else:
        app.logger.debug(s)

app = Flask(__name__)

builtins.app = app           # so it's available to other modules.

app.config.from_object('config')
os.environ['FLASK_SETTINGS'] = '/home/hugh9/settings.cfg'
debug('FLASK_SETTINGS is '+os.environ['FLASK_SETTINGS'])
app.config.from_envvar('FLASK_SETTINGS')
app.secret_key = os.urandom(24)
mysql = MySQL()
mysql.init_app(app)

datarange = None

def browseprevmonth(year,month):
    (year, month) = (int(year), int(month))
    (year, month) = (year, month-1) if month != 1 else (year-1, 12)
    return url_for('browseym',year=year,month=month)

def browsenextmonth(year,month):
    (year, month) = (int(year), int(month))
    (year,month) = (year, month+1) if month != 12 else (year+1, 1)
    return url_for('browseym',year=year,month=month)

@app.route('/browseym/')
@app.route('/browseym/<year>/<month>')
def browseym(year=2017,month=2):
    data = pandb.get_data_json(year,month)
    print(('len(data) is ',len(data)))
    return render_template('browse.html',
                           version = app.config['VERSION'],
                           display_date = str(month)+'/'+str(year),
                           prev_month = browseprevmonth(year,month),
                           next_month = browsenextmonth(year,month),
                           data = data)
                           
@app.route('/browse/')
@app.route('/browse/<datestr>')
def browse(datestr=None):
    if datestr is not None:
        try:
            dateobj = pandb.to_date(datestr)
            displaydate = datetime.strftime(dateobj,'%A %B %d, %Y')
        except:
            flash('bad date')
            datestr = None
            displaydate = 'all'
    else:
        displaydate = 'all'
    return render_template('browse.html',
                           version = app.config['VERSION'],
                           displaydate = displaydate,
                           data = pandb.get_data_json(None,None))
                           

@app.route('/plot1/')
@app.route('/plot1/<datestr>')
def plot1(datestr=None):
    flash('plot1 is obsolete')
    return redirect(url_for('plot2',datestr=datestr))

@app.route('/plot2/')
@app.route('/plot2/<datestr>')
def plot2(datestr=None):
    debug('================================================================\nstarting plot2, args is %s' % str(request.args))
    debug('debug message')
    # cleans up the URL
    if request.method == 'GET' and request.args.get('date') != None:
        debug('redirecting to clean url', url_for('plot2', datestr=request.args.get('date')))
        return redirect(url_for('plot2', datestr=request.args.get('date')))
    compute_data_range()
    if not datestr:
        print('rendering page w/o datestr')
        return render_template('base.html',
                               version = app.config['VERSION'],
                               page_title = 'CGM and IC lookup',
                               datarange = datarange)
    try:
        date = datetime.strptime(datestr,'%Y-%m-%d')
    except:
        return render_template('base.html',
                               version = app.config['VERSION'],
                               page_title = 'CGM and IC lookup',
                               datarange = datarange)

    debug('handling date %s ' % str(date))
    curs = mysql.connection.cursor()
    calcs = pandb.compute_ic_and_excess_bg_for_date(date, conn=mysql.connection)
    print('back from pandb, calculated the following values:')
    print((list(calcs.keys())))
    # mysql.connection.close()
    dateObj = datetime.strptime(datestr, '%Y-%m-%d')
    datePretty = dateObj.strftime('%A, %B %d, %Y')
    yesterday = datetime.strftime(dateObj+timedelta(-1,0,0), '%Y-%m-%d')
    url_yesterday = url_for('plot2',datestr=yesterday)
    tomorrow = datetime.strftime(dateObj+timedelta(+1,0,0), '%Y-%m-%d')
    url_tomorrow = url_for('plot2',datestr=tomorrow)
    if 'initial_ic' in calcs:
        print(('in plot2, I:C is %s' % str(calcs['initial_ic'])))
    else:
        print("in plot2, I:C couldn't be calculated")

    if False:
        ic_trace = go.Scatter( x = calcs['meal_time'],
                               y = calcs['initial_ic'],
                               name = 'IC initial',
                               mode = 'markers',
                               yaxis = 'y2')
    cgm_data = calcs['cgm_data']
    times = cgm_data['times']
    xmin = times[0]
    xmax = times[-1]
    trace = go.Scatter( x = cgm_data['times'], y=cgm_data['vals'], name='cgm')
    traces = [trace]
    start = util.iso_to_readable(xmin)
    end = util.iso_to_readable(xmax)
    layout = go.Layout( title = ('blood glucose showing {n} values from {start} to {end}'
                                 .format(n=len(cgm_data['vals']),
                                         start=start,end=end)),
                        yaxis = dict(title='mg per dl',
                                     # the y zeroline is the line where y=0
                                     zeroline=True,
                                     zerolinecolor='#800000',
                                     zerolinewidth=2,
                                     # this is the vertical line at the left edge
                                     showline=False,
                                     rangemode='tozero'),
                        xaxis = dict(title='time of day',
                                     showline=True,
                                     zeroline=True)
                        )
    # add basals and boluses
    add_basal_insulin_and_bolus_insulin = True
    if add_basal_insulin_and_bolus_insulin:
        basal_trace = go.Scatter( x = [ d['time']
                                        for d in calcs['extra_insulin_data' ]],
                                  y = [ d['basal']
                                        for d in calcs['extra_insulin_data' ]],
                                  name = 'basal',
                                  mode = 'markers',
                                  marker = dict( color = 'orange', size=6 ),
                                  yaxis = 'y2')
        traces.append(basal_trace)
        bolus_trace = go.Scatter( x = [ d['time']
                                        for d in calcs['bolus_data' ]],
                                  y = [ d['bolus_volume']
                                        for d in calcs['bolus_data' ]],
                                  name = 'bolus_volume',
                                  marker = dict( color = 'red', size=12 ),
                                  mode = 'markers',
                                  yaxis = 'y2')
        traces.append(bolus_trace)
        layout.update(yaxis2=dict( title='insulin',
                                   overlaying='y',
                                   side='right'))

    # add transparent rectangle for ideal bg
    layout.update(dict(shapes = [ {
        'type': 'rect',
        'xref': 'x',
        'yref': 'y',
        'x0': xmin,
        'x1': xmax,
        'y0': 80,
        'y1': 120,
        'fillcolor': '#ccffcc',
        'opacity': '0.4',
        'line': {'width':2,'color':'#ccffcc'}
        } ]) )
    graph = go.Figure(data = traces, layout = layout)
    graphJSON = json.dumps( graph, cls=plotly.utils.PlotlyJSONEncoder)
    print('in plot2, about to render template')
    return render_template('main2.html',
                           version = app.config['VERSION'],
                           page_title='Minerva',
                           graphJSON = graphJSON,
                           calcs = calcs,
                           record_date = datePretty,
                           url_tomorrow = url_tomorrow,
                           current_date = datestr,
                           url_yesterday = url_yesterday,
                           datarange = datarange
                           )


# this function *can't* be invoked from global context. the flask_mysqldb
# wrapper only allows connections from requests, so that they are
# thread-local. This is mostly a good thing, but annoying.

# whoami()

@app.route('/')
def hello_world():
    compute_data_range()
    return render_template('base.html', 
                           version = app.config['VERSION'],
                           page_title = 'CGM and IC lookup',
                           datarange = datarange)


@app.route('/ic/')
@app.route('/ic/<date>')
def ic_display(date=None):
    # cleans up the URL
    if request.method == 'GET' and request.args.get('ic_date') != None:
        debug('redirecting to clean url', url_for('ic_display', date=request.args.get('ic_date')))
        return redirect(url_for('ic_display', date=request.args.get('ic_date')))
    if not date:
        return render_template('main.html',
                               version = app.config['VERSION'],
                               page_title = 'CGM and IC lookup',
                               cols = [],
                               current_date = '',
                               record_date = '',
                               records = [])
    curs = mysql.connection.cursor()
    cols = ['time','carbs','bolus_type','bolus_volume','notes']
    records = db.getICByDate(date,cols,curs)
    dateObj = datetime.strptime(date, '%Y-%m-%d')
    dateStr = dateObj.strftime('%A, %B %d, %Y')
    return render_template('main.html',
                           version = app.config['VERSION'],
                           page_title = 'IC lookup for '+date,
                           current_date = dateObj.strftime('%m/%d/%Y'),
                           cols = cols,
                           record_date = dateStr,
                           records = records)
                           
    
@app.route('/cgm/')
@app.route('/cgm/<date>')
def cgm_display(date=None):
    return render_template('main.html',
                           version = app.config['VERSION'],
                           page_title='CGM for '+date)
    
def compute_data_range():
    global datarange
    if not datarange:
        (min_ic, max_ic) = db.insulin_carb_data_range()
        (min_cgm, max_cgm) = db.cgm_data_range()
        datarange = dict()
        datarange['max_ic'] = max_ic
        datarange['min_ic'] = min_ic
        datarange['max_cgm'] = max_cgm



        debug('data range is %s' % str(datarange))

@app.route('/browseisf/')
@app.route('/browseisf/<date>/', methods = ['GET','POST'])
def browse_isf(date=None):
    '''Displays information (bg,cgm,bolus) for the 2.5hr span after corrective insulin given '''
    if request.method == "GET": 
        if date == None:
            dtime = '2018-01-01 05:50'
        else:
            dtime = date
        rows = isf.get_isf(dtime)
    else:
        rows = isf.get_isf(date)
        dtime = rows[0]['rtime']
        time = dtime.strftime('%m-%d-%y %H:%M')
        if rows[0]['ISF_trouble'] == 'ok':
            return render_template('isf.html',
                                   isf_trouble = None,
                                   script = url_for('browse_isf', date = dtime),
                                   rows = rows,
                                   dtime = dtime,
                                   page_title ='ISF for ' + time)

        else:
            return render_template('isf.html',
                                   isf_trouble = rows[0]['ISF_trouble'],
                                   script = url_for('browse_isf', date =dtime),
                                   rows = rows,
                                   dtime = dtime,
                                   page_title = 'ISF for ' + time)
    return render_template ('isf.html',
                            isf_trouble = None,
                            script = url_for('browse_isf', date = dtime),
                            rows = rows,
                            time = dtime, 
                            page_title ='ISF for ' +dtime) 
    
# this route uses a slash instead of the space, which looks like %20 in the URL
# it also looks up the exact date, instead of the *next* one.
@app.route('/browseisf2/')
@app.route('/browseisf2/<date>/')
@app.route('/browseisf2/<date>/<time>', methods = ['GET','POST'])
def browse_isf2(date=None,time=None):
    # not sufficiently general, but okay for now
    first = isf.get_first_corrective_insulin(year=2018)
    first_date, first_time = (first.strftime('%Y-%m-%d'), first.strftime('%H:%M:%S'))
    if date == None:
        date,time = first_date,first_time
    elif time == None:
        date = first_date
    try:
        rtime_str,rtime_dt = date_ui.to_datestr(date,time)
    except:
        flash('invalid date: {} {}'.format(date,time))
        return redirect(url_for('browse_isf2'))
    print(('browsing w/ start time = {}'.format(rtime_str)))

    if request.method == "POST":
        # POST almost certainly means the user clicked the "next" button
        # we'll assume that
        conn = get_conn()
        print(('getting next ISF after {}'.format(rtime_str)))
        start_dt = isf.get_isf_next(conn,rtime_str)
        return redirect(url_for('browse_isf2',
                                date=start_dt.strftime('%Y-%m-%d'),
                                time=start_dt.strftime('%H:%M:%S')))
    else:
        conn = get_conn()
        rows = isf.get_isf_at(conn,rtime_str)
        trouble = rows[0]['ISF_trouble']
        # convert 'ok' to empty
        trouble = '' if trouble == 'ok' else trouble
        details = isf.get_isf_details(conn,rtime_dt)
        return render_template('isf2.html',
                               isf_trouble = trouble,
                               script = url_for('browse_isf2',
                                                date = rtime_dt.strftime('%Y-%m-%d'),
                                                time = rtime_dt.strftime('%H:%M:%S')),
                               rows = rows,
                               details = details,
                               # decoration
                               page_title = ('''ISF for {dt:%A}, 
                                                {dt:%B} {dt.day}, {dt.year},
                                                at {dt.hour}:{dt.minute:02d}'''
                                             .format(dt=rtime_dt)))
    

@app.route('/isfcompareEarlyLate/')
def isf_compare():
    '''shows 2014-2016 versus 2017-2018 but each time bucket is its own plot
so the early/late distributions can be easily compared.'''
    (all_before, bucket_list_before) = isf.get_isf_for_years('2014', '2016')
    allData_before = [data[0] for data in all_before if data[0]]

    before_1 = go.Box(y = bucket_list_before[0], name = "'14-'16")
    before_2 = go.Box(y = bucket_list_before[1], name = "'14-'16")
    before_3 = go.Box(y = bucket_list_before[2], name = "'14-'16")
    before_4 = go.Box(y = bucket_list_before[3], name = "'14-'16")
    before_5 = go.Box(y = bucket_list_before[4], name = "'14-'16")
    before_6 = go.Box(y = bucket_list_before[5], name = "'14-'16")
    before_7 = go.Box(y = bucket_list_before[6], name = "'14-'16")
    before_8 = go.Box(y = bucket_list_before[7], name = "'14-'16")
    before_9 = go.Box(y = bucket_list_before[8], name = "'14-'16")
    before_10 = go.Box(y = bucket_list_before[9], name = "'14-'16")
    before_11 = go.Box(y = bucket_list_before[10], name = "'14-'16")
    before_12 = go.Box(y = bucket_list_before[11], name = "'14-'16")

    (all_after, bucket_list_after) = isf.get_isf_for_years('2016', '2018')
    allData_after = [data[0] for data in all_after if data[0]]

    after_1 = go.Box(y = bucket_list_after[0], name = "'16-'18")
    after_2 = go.Box(y = bucket_list_after[1], name = "'16-'18")
    after_3 = go.Box(y = bucket_list_after[2], name = "'16-'18")
    after_4 = go.Box(y = bucket_list_after[3], name = "'16-'18")
    after_5 = go.Box(y = bucket_list_after[4], name = "'16-'18")
    after_6 = go.Box(y = bucket_list_after[5], name = "'16-'18")
    after_7 = go.Box(y = bucket_list_after[6], name = "'16-'18")
    after_8 = go.Box(y = bucket_list_after[7], name = "'16-'18")
    after_9 = go.Box(y = bucket_list_after[8], name = "'16-'16")
    after_10 = go.Box(y = bucket_list_after[9], name = "'16-'18")
    after_11 = go.Box(y = bucket_list_after[10], name = "'16-'18")
    after_12 = go.Box(y = bucket_list_after[11], name = "'16-'18")

    yaxis_dict = dict(title = 'mgdl/unit',
                      zeroline = True,
                      zerolinecolor = '#800000',
                      showline = False,
                      rangemode = 'tozero')

    layout_0am = go.Layout(title = ('isf values from 0am-2am'), width = 1000, height = 800,
                           yaxis = yaxis_dict )
    graph_0am = go.Figure(data = [before_1, after_1], layout = layout_0am)
    graphJSON0am = json.dumps(graph_0am, cls= plotly.utils.PlotlyJSONEncoder)

    layout_2am = go.Layout(title = ('isf values from 2am-4am'), width = 1000, height = 800,
                           yaxis = yaxis_dict)
    graph_2am = go.Figure(data = [before_2, after_2], layout = layout_2am)
    graphJSON2am = json.dumps(graph_2am, cls = plotly.utils.PlotlyJSONEncoder)

    layout_4am = go.Layout(title = ('isf values from 4am-6am'), width = 1000, height = 800,
                           yaxis = yaxis_dict)
    graph_4am = go.Figure(data = [before_3, after_3], layout = layout_4am)
    graphJSON4am = json.dumps(graph_4am, cls = plotly.utils.PlotlyJSONEncoder)

    layout_6am = go.Layout(title = ('isf values from 6am-8am'), width = 1000, height = 800,
                           yaxis = yaxis_dict)
    graph_6am = go.Figure(data = [before_4, after_4], layout = layout_6am)
    graphJSON6am = json.dumps(graph_6am, cls = plotly.utils.PlotlyJSONEncoder)

    layout_8am = go.Layout(title = ('isf values from 8am-10am'), width = 1000, height = 800,
                           yaxis = yaxis_dict)
    graph_8am = go.Figure(data =[before_5, after_5], layout = layout_8am)
    graphJSON8am = json.dumps(graph_8am, cls = plotly.utils.PlotlyJSONEncoder)

    layout_10am = go.Layout(title = ('isf values from 10am-12pm'), width = 1000, height = 800,
                            yaxis = yaxis_dict)
    graph_10am = go.Figure(data = [before_6, after_6], layout = layout_10am)
    graphJSON10am = json.dumps (graph_10am, cls = plotly.utils.PlotlyJSONEncoder)

    layout_12pm = go.Layout(title = ('isf values from 12pm-2pm'), width = 1000, height = 800,
                            yaxis = yaxis_dict)
    graph_12pm = go.Figure(data = [before_7, after_7], layout = layout_12pm)
    graphJSON12pm = json.dumps(graph_12pm, cls = plotly.utils.PlotlyJSONEncoder)

    layout_2pm = go.Layout(title = ('isf values from 2pm - 4pm'), width = 1000, height = 800,
                           yaxis = yaxis_dict)
    graph_2pm = go.Figure(data = [before_8, after_8], layout = layout_2pm)
    graphJSON2pm = json.dumps (graph_2pm, cls = plotly.utils.PlotlyJSONEncoder)

    layout_4pm = go.Layout(title = ('isf values from 4pm-6pm'), width = 1000, height = 800,
                            yaxis = yaxis_dict)
    graph_4pm = go.Figure(data = [before_9, after_9], layout = layout_4pm)
    graphJSON4pm = json.dumps(graph_4pm, cls = plotly.utils.PlotlyJSONEncoder)

    layout_6pm = go.Layout(title = ('isf values from 6pm - 8pm'), width = 1000, height = 800,
                           yaxis = yaxis_dict)
    graph_6pm = go.Figure (data = [before_10, after_10], layout = layout_6pm)
    graphJSON6pm = json.dumps (graph_6pm, cls = plotly.utils.PlotlyJSONEncoder)

    layout_8pm = go.Layout(title = ('isf values from 8pm-10pm'), width = 1000, height = 800,
                           yaxis = yaxis_dict)
    graph_8pm = go.Figure(data = [before_11,after_11], layout = layout_8pm)
    graphJSON8pm = json.dumps(graph_8pm,cls=plotly.utils.PlotlyJSONEncoder)

    layout_10pm = go.Layout(title = ('isf values from 10pm-12am'), width = 1000, height = 800,
                            yaxis = yaxis_dict)
    graph_10pm = go.Figure(data=[before_12, after_12], layout = layout_10pm)
    graphJSON10pm = json.dumps(graph_10pm, cls = plotly.utils.PlotlyJSONEncoder)


    return render_template('isfcompare.html',
                           version = app.config['VERSION'],
                           page_title = 'Minerva Compare ISF Values',
                           graphJSON_0am = graphJSON0am,
                           graphJSON_2am = graphJSON2am,
                           graphJSON_4am = graphJSON4am,
                           graphJSON_6am = graphJSON6am,
                           graphJSON_8am = graphJSON8am,
                           graphJSON_10am = graphJSON10am,
                           graphJSON_12pm = graphJSON12pm,
                           graphJSON_2pm = graphJSON2pm,
                           graphJSON_4pm = graphJSON4pm,
                           graphJSON_6pm = graphJSON6pm,
                           graphJSON_8pm = graphJSON8pm,
                           graphJSON_10pm = graphJSON10pm) 
                     
@app.route('/isfcompareBG/')
def isf_compare_bg():
    '''Displays ISF data in a box-and-whisker plot comparing data with starting BG less than 200 and starting BG greater than 200 '''
    (less_than, greater_than) = isf.get_isf_for_bg('200')

    less_than_1 = go.Box(y = less_than[0], name = "bg<200")
    less_than_2 = go.Box(y = less_than[1], name = "bg<200")
    less_than_3 = go.Box(y = less_than[2], name = "bg<200")
    less_than_4 = go.Box(y = less_than[3], name = "bg<200")
    less_than_5 = go.Box(y = less_than[4], name = "bg<200")
    less_than_6 = go.Box(y = less_than[5], name = "bg<200")
    less_than_7 = go.Box(y = less_than[6], name = "bg<200")
    less_than_8 = go.Box(y = less_than[7], name = "bg<200")
    less_than_9 = go.Box(y = less_than[8], name = "bg<200")
    less_than_10 = go.Box(y = less_than[9], name = "bg<200")
    less_than_11 = go.Box(y = less_than[10], name = "bg<200")
    less_than_12 = go.Box(y = less_than[11], name = "bg<200")

    greater_than_1 = go.Box(y = greater_than[0], name = "bg>200")
    greater_than_2 = go.Box(y = greater_than[1], name = "bg>200")
    greater_than_3 = go.Box(y = greater_than[2], name = "bg>200")
    greater_than_4 = go.Box(y = greater_than[3], name = "bg>200")
    greater_than_5 = go.Box(y = greater_than[4], name = "bg>200")
    greater_than_6 = go.Box(y = greater_than[5], name = "bg>200")
    greater_than_7 = go.Box(y = greater_than[6], name = "bg>200")
    greater_than_8 = go.Box(y = greater_than[7], name = "bg>200")
    greater_than_9 = go.Box(y = greater_than[8], name = "bg>200")
    greater_than_10 = go.Box(y = greater_than[9], name = "bg>200")
    greater_than_11 = go.Box(y = greater_than[10], name = "bg>200")
    greater_than_12 = go.Box(y = greater_than[11], name = "bg>200")

    yaxis_dict = dict(title = "mgdl/unit",
                      zeroline = True,
                      zerolinecolor = '#800000',
                      showline = False,
                      rangemode = 'tozero')

    layout_0am = go.Layout(title = ('isf values from 0am-2am'), width = 1000, height = 800, yaxis = yaxis_dict)
    graph_0am = go.Figure(data = [less_than_1, greater_than_1], layout = layout_0am)
    graphJSON0am = json.dumps(graph_0am,  cls= plotly.utils.PlotlyJSONEncoder)

    layout_2am = go.Layout(title = ('isf values from 2am-4am'), width = 1000, height = 800, yaxis = yaxis_dict)
    graph_2am = go.Figure(data = [less_than_2, greater_than_2], layout = layout_2am)
    graphJSON2am = json.dumps(graph_2am, cls = plotly.utils.PlotlyJSONEncoder)

    layout_4am = go.Layout(title = ('isf values from 4am-6am'), width = 1000, height = 800, yaxis = yaxis_dict)
    graph_4am = go.Figure(data = [less_than_3, greater_than_3], layout = layout_4am)
    graphJSON4am = json.dumps(graph_4am, cls = plotly.utils.PlotlyJSONEncoder)

    layout_6am = go.Layout(title = ('isf values from 6am-8am'), width = 1000, height = 800, yaxis = yaxis_dict)
    graph_6am = go.Figure(data = [less_than_4, greater_than_4], layout = layout_6am)
    graphJSON6am = json.dumps(graph_6am, cls = plotly.utils.PlotlyJSONEncoder)

    layout_8am =  go.Layout(title = ('isf values from 8am-10am'), width = 1000,height= 800, yaxis = yaxis_dict)
    graph_8am = go.Figure(data = [less_than_5, greater_than_5], layout = layout_8am)
    graphJSON8am = json.dumps(graph_8am, cls = plotly.utils.PlotlyJSONEncoder) 

    layout_10am = go.Layout (title = ('isf values from 10am-12pm'), width = 1000, height = 800, yaxis = yaxis_dict)
    graph_10am = go.Figure (data = [less_than_6, greater_than_6], layout = layout_10am)
    graphJSON10am = json.dumps (graph_10am, cls = plotly.utils.PlotlyJSONEncoder)

    layout_12pm = go.Layout(title = ('isf values from 12pm-2pm'), width = 1000, height = 800, yaxis = yaxis_dict)
    graph_12pm = go.Figure(data = [less_than_7, greater_than_7], layout = layout_12pm)
    graphJSON12pm = json.dumps(graph_12pm, cls = plotly.utils.PlotlyJSONEncoder)

    layout_2pm = go.Layout(title = ('isf values from 2pm-4pm'), width = 1000, height = 800, yaxis = yaxis_dict)
    graph_2pm = go.Figure(data = [less_than_8, greater_than_8], layout = layout_2pm)
    graphJSON2pm = json.dumps (graph_2pm, cls = plotly.utils.PlotlyJSONEncoder)

    layout_4pm = go.Layout(title = ('isf values from 4pm-6pm'), width = 1000, height = 800, yaxis = yaxis_dict)
    graph_4pm = go.Figure(data = [less_than_9, greater_than_9], layout = layout_4pm)
    graphJSON4pm = json.dumps(graph_4pm, cls = plotly.utils.PlotlyJSONEncoder)

    layout_6pm = go.Layout(title = ('isf values from 6pm-8pm'), width = 1000, height = 800, yaxis = yaxis_dict)
    graph_6pm = go.Figure(data = [less_than_10, greater_than_10], layout = layout_6pm)
    graphJSON6pm = json.dumps (graph_6pm, cls = plotly.utils.PlotlyJSONEncoder)

    layout_8pm = go.Layout(title = ('isf values from 8pm-10pm'), width = 1000, height = 800, yaxis = yaxis_dict)
    graph_8pm = go.Figure(data = [less_than_11, greater_than_12], layout = layout_8pm)
    graphJSON8pm = json.dumps(graph_8pm,cls=plotly.utils.PlotlyJSONEncoder)

    layout_10pm = go.Layout(title = ('isf values from 10pm-12am'), width = 1000, height = 800, yaxis = yaxis_dict)
    graph_10pm = go.Figure(data = [less_than_12, greater_than_12], layout = layout_10pm)
    graphJSON10pm = json.dumps(graph_10pm, cls = plotly.utils.PlotlyJSONEncoder)

    return render_template('isfcompare.html',
                            version = app.config['VERSION'],
                            page_title = 'Minerva Compare ISF Values',
                            graphJSON_0am = graphJSON0am,
                            graphJSON_2am = graphJSON2am,
                            graphJSON_4am = graphJSON4am,
                            graphJSON_6am = graphJSON6am,
                            graphJSON_8am = graphJSON8am,
                            graphJSON_10am = graphJSON10am,
                            graphJSON_12pm = graphJSON12pm,
                            graphJSON_2pm = graphJSON2pm,
                            graphJSON_4pm = graphJSON4pm,
                            graphJSON_6pm = graphJSON6pm,
                            graphJSON_8pm = graphJSON8pm,
                            graphJSON_10pm = graphJSON10pm) 
    
@app.teardown_appcontext
def teardown_db(exception):
    conn = getattr(g, 'conn', None)
    if conn is not None:
        conn.close()

if __name__ == '__main__':
    port = 1942
    print('starting')
    app.debug = True
    if not app.debug:
        print('unlinking old logfile')
        os.unlink(LOGFILE)
    logHandler = RotatingFileHandler(LOGFILE, maxBytes=10000, backupCount=1)
    logHandler.setLevel(LOGLEVEL)
    app.logger.setLevel(LOGLEVEL)
    app.logger.addHandler(logHandler)
    print('about to try debug statement')
    debug('Debug is %s' % app.debug)
    debug('Version is %s' % app.config['VERSION'])
    app.run('0.0.0.0',port=port)
