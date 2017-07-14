# A very simple Flask Hello World app for you to get started with...

import os
from flask import (Flask, render_template, make_response, request, redirect, url_for,
                   session, flash, send_from_directory)
from werkzeug import secure_filename

import time
import logging

LOGFILE='app.log'
LOGLEVEL=logging.DEBUG

from logging.handlers import RotatingFileHandler

from flask_mysqldb import MySQL
from datetime import datetime, timedelta
import db

import json
import plotly
import plotly.plotly as py
import plotly.graph_objs as go

import util

import __builtin__

app = Flask(__name__)

__builtin__.app = app           # so its available to other modules.

app.config.from_object('config')
app.config.from_envvar('FLASK_SETTINGS')
app.secret_key = os.urandom(24)
mysql = MySQL()
mysql.init_app(app)

datarange = None

@app.route('/plot1/')
@app.route('/plot1/<datestr>')
def plot1(datestr=None):
    debug('================================================================\nstarting plot1, args is %s' % str(request.args))
    debug('debug message')
    # cleans up the URL
    if request.method == 'GET' and request.args.get('date') != None:
        debug('redirecting to clean url', url_for('plot1', datestr=request.args.get('date')))
        return redirect(url_for('plot1', datestr=request.args.get('date')))
    compute_data_range()
    if not datestr:
        return render_template('main.html',
                               page_title = 'CGM and IC lookup',
                               cols = [],
                               current_date = '',
                               record_date = '',
                               records = [],
                               datarange = datarange)
    try:
        date = datetime.strptime(datestr,'%Y-%m-%d')
    except:
        flash('invalid date: '+datestr)
        return render_template('main.html',
                               page_title = 'CGM and IC lookup',
                               cols = [],
                               current_date = '',
                               record_date = '',
                               records = [],
                               datarange = datarange)

    debug('handling date %s ' % str(date))
    curs = mysql.connection.cursor()
    plotdict = db.plotCGMByDate(date,curs)
    ic_initial = db.getICByDate(date,curs)
    raw = db.getICByDateRaw(db.strip_hyphens(datestr),curs)
    cols = ['rec_num','date_time','Basal_amt',
            'temp_basal_down','temp_basal_up','temp_basal_duration',
            'bolus_type','bolus_volume',
            'Immediate_percent','extended_percent',
            'duration','carbs','notes']
    db.remove_empty_cols(cols,raw)
    # rawtable = db.makeTableHTML(cols, raw)
    mealtable = db.makeTableHTML(['when','carbs','bolus','ratio','basis'],ic_initial)
    dateObj = datetime.strptime(datestr, '%Y-%m-%d')
    datePretty = dateObj.strftime('%A, %B %d, %Y')
    yesterday = datetime.strftime(dateObj+timedelta(-1,0,0), '%Y-%m-%d')
    url_yesterday = url_for('plot1',datestr=yesterday)
    tomorrow = datetime.strftime(dateObj+timedelta(+1,0,0), '%Y-%m-%d')
    url_tomorrow = url_for('plot1',datestr=tomorrow)
    ic_trace = go.Scatter( x = db.col(ic_initial,'time'),
                           y = db.col(ic_initial,'ratio'),
                           name = 'IC initial',
                           mode = 'markers',
                           yaxis = 'y2')
    debug('times: %s' % str(db.col(ic_initial,'time')))
    debug('ratios: %s' % str(db.col(ic_initial,'ratio')))
    if plotdict == None:
        print('No CGM data for this date')
        flash('No CGM data for this date')
        data = []
    else:
        data = plotdict['data']
    data.append(ic_trace)
    layout = go.Layout( title = 'glucose and IC',
                        yaxis = dict(title='mg per dl'),
                        yaxis2 = dict(title='IC',
                                      overlaying='y',
                                      side='right'))
    graph = go.Figure(data = data, layout = layout)
    graphJSON = json.dumps( graph, cls=plotly.utils.PlotlyJSONEncoder)
    return render_template('main.html',
                           page_title='Minerva',
                           graphJSON = graphJSON,
                           table1 = mealtable,
                           cols = cols,
                           records = raw,
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
    return render_template('main.html', page_title='Minerva',
                           datarange=datarange
                           )

@app.route('/ic/')
@app.route('/ic/<date>')
def ic_display(date=None):
    # cleans up the URL
    if request.method == 'GET' and request.args.get('ic_date') != None:
        debug('redirecting to clean url', url_for('ic_display', date=request.args.get('ic_date')))
        return redirect(url_for('ic_display', date=request.args.get('ic_date')))
    if not date:
        return render_template('main.html',
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
                           page_title = 'IC lookup for '+date,
                           current_date = dateObj.strftime('%m/%d/%Y'),
                           cols = cols,
                           record_date = dateStr,
                           records = records)
                           
    
@app.route('/cgm/')
@app.route('/cgm/<date>')
def cgm_display(date=None):
    return render_template('main.html',
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
        datarange['min_cgm'] = min_cgm
        debug('data range is %s' % str(datarange))

def debug(*args):
    s = ' '.join(map(str,args))
    if app.debug:
        print "debug: "+s
    else:
        app.logger.debug(s)

if __name__ == '__main__':
    port = 1942
    if not app.debug:
        os.unlink(LOGFILE)
    logHandler = RotatingFileHandler(LOGFILE, maxBytes=10000, backupCount=1)
    logHandler.setLevel(LOGLEVEL)
    app.logger.setLevel(LOGLEVEL)
    app.logger.addHandler(logHandler)
    debug('Debug is %s' % app.debug)
    app.run('0.0.0.0',port=port)
