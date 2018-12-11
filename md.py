import os
from flask import (Flask, render_template, make_response, request, redirect, url_for,
                   session, flash, send_from_directory, g)
from werkzeug import secure_filename

import time
import logging
import random

LOGFILE='app.log'
LOGLEVEL=logging.DEBUG

from logging.handlers import RotatingFileHandler

from flask_mysqldb import MySQL
from datetime import datetime, timedelta
import db
import pandb
import isf

import json
import plotly
import plotly.plotly as py
import plotly.graph_objs as go

import util

import __builtin__

def debug(*args):
    s = ' '.join(map(str,args))
    if app.debug:
        print "debug: "+s
    else:
        app.logger.debug(s)

app = Flask(__name__)

__builtin__.app = app           # so it's available to other modules.

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
    print('len(data) is ',len(data))
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
    print(calcs.keys())
    # mysql.connection.close()
    dateObj = datetime.strptime(datestr, '%Y-%m-%d')
    datePretty = dateObj.strftime('%A, %B %d, %Y')
    yesterday = datetime.strftime(dateObj+timedelta(-1,0,0), '%Y-%m-%d')
    url_yesterday = url_for('plot2',datestr=yesterday)
    tomorrow = datetime.strftime(dateObj+timedelta(+1,0,0), '%Y-%m-%d')
    url_tomorrow = url_for('plot2',datestr=tomorrow)
    if 'initial_ic' in calcs:
        print('in plot2, I:C is %s' % str(calcs['initial_ic']))
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
    
    
@app.route('/isfplots/')
def isfplots():
    (all, bucket_list) = isf.get_all_isf_plus_buckets()
    allData = [data[0] for data in all if data[0]]
    print bucket_list[5]
    all_whisker = go.Box( y = allData, name = 'all isf')
    bucket0 = go.Box(y = bucket_list[0], name = '0am-2am')
    bucket1 = go.Box(y = bucket_list[1], name = '2am-4am')
    bucket2 = go.Box(y = bucket_list[2], name = '4am-6am')
    bucket3 = go.Box(y = bucket_list[3], name = '6am-8am')
    bucket4 = go.Box(y = bucket_list[4], name = '8am-10am')
    bucket5 = go.Box(y = bucket_list[5], name = '10am-12pm')
    bucket6 = go.Box(y = bucket_list[6], name = '12pm-14pm')
    bucket7 = go.Box(y = bucket_list[7], name = '14pm-16pm')
    bucket8 = go.Box(y = bucket_list[8], name = '16pm-18pm')
    bucket9 = go.Box(y = bucket_list[9], name = '18pm-20pm')
    bucket10 = go.Box(y = bucket_list[10], name = '20pm-22pm')
    bucket11 = go.Box(y = bucket_list[11], name = '22pm-24pm')
    layout = go.Layout( title = ('isf values'), width = 1500,height = 1000,
                        yaxis = dict(title='mgdl/unit',
                                     # the y zeroline is the line where y=0
                                     zeroline=True,
                                     zerolinecolor='#800000',
                                     zerolinewidth=2,
                                     # this is the vertical line at the left edge
                                     showline=False,
                                     rangemode='tozero')
                        )
    graph = go.Figure(data = [all_whisker,bucket0,bucket1,bucket2,bucket3
                              ,bucket4,bucket5
                              ,bucket6,bucket7,bucket8,bucket9,bucket10,bucket11]
                             ,layout = layout)
    graphJSON = json.dumps( graph, cls=plotly.utils.PlotlyJSONEncoder)
    return render_template('isfplots.html',
                           version = app.config['VERSION'],
                           page_title='Minerva ISF values',
                           graphJSON = graphJSON)


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
