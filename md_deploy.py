import os, sys
from flask import (Flask, render_template, make_response, request, redirect, url_for,
                   session, flash, send_from_directory, g)
from flask import jsonify

import time
import logging
import random
import math

'''Deployed app'''

LOGFILE='md_deploy.log'
LOGLEVEL=logging.DEBUG

from logging.handlers import RotatingFileHandler

from flaskext.mysql import MySQL

from datetime import datetime, timedelta
import json

import cs304dbi as dbi
import isf2 as isf
import date_ui
# need a better place for this function
import ics
import util

# import builtins

def debug(*args):
    s = ' '.join(map(str,args))
    if app.debug:
        print(("debug: "+s))
    else:
        app.logger.debug(s)

app = Flask(__name__)

# builtins.app = app           # so it's available to other modules.

app.config.from_object('config')
os.environ['FLASK_SETTINGS'] = '/home/hugh9/settings.cfg'
debug('FLASK_SETTINGS is '+os.environ['FLASK_SETTINGS'])
app.config.from_envvar('FLASK_SETTINGS')
app.secret_key = os.urandom(24)
mysql = MySQL()
mysql.init_app(app)

@app.route('/')
def displayRecentISF():
    '''This just displays the page; all the data is gotten by Ajax. See below.'''
    return render_template('isf-display.html')

@app.route('/info/')
def info():
    '''Info about the app deployment'''
    flash('Python version is {}'.format(sys.version))
    for p in sys.path:
        flash('Path has {}'.format(p))
    flash('Python sys.prefix is {}'.format(sys.prefix))
    return render_template('b.html')


# Plots of insulin and cgm, and, eventually, predictive model.

DEFAULT_HOURS = 2

@app.route('/plots/')
def plots0():
    '''Plots for most recent two hours (DEFAULT_HOURS)'''
    start_datetime = datetime.now() - timedelta(hours=DEFAULT_HOURS)
    start_rtime = date_ui.to_rtime(start_datetime)
    start_date = start_rtime.strftime('%Y-%m-%d')
    start_time = start_rtime.strftime('%H:%M')
    return redirect(url_for('plots2',
                            start_date = start_date,
                            start_time = start_time,
                            hours = DEFAULT_HOURS))

@app.route('/plots/<start_date>/<start_time>/<hours>')
def plots2(start_date, start_time, hours):
    '''Plots of insulin and cgm, and, eventually, predictive
model, starting at given date and time and for given number of hours.'''
    # can't trust the user's start_time
    try:
        start_datetime = date_ui.to_rtime(start_date + " " + start_time)
        start_rtime = date_ui.to_rtime(start_datetime)
        start_date = start_rtime.strftime('%Y-%m-%d')
        start_time = start_rtime.strftime('%H:%M')
    except ValueError:
        flash('bad start time. Use format YYYY-MM-DD HH:MM; using now instead')
        ## code is same as plots0
        start_datetime = datetime.now() - timedelta(hours=DEFAULT_HOURS)
        start_rtime = date_ui.to_rtime(start_datetime)
        start_date = start_rtime.strftime('%Y-%m-%d')
        start_time = start_rtime.strftime('%H:%M')
        return redirect(url_for('plots2',
                                start_date = start_date,
                                start_time = start_time,
                                hours = DEFAULT_HOURS))

    # finally, a useful response. However, the actual data is sent by Ajax.
    return render_template('plots.html', start_date=start_date, start_time=start_time, hours=hours)

@app.route('/plot-data/')
def plot_data0():
    '''Gets the current data as an JSON response'''
    start = date_ui.to_rtime(datetime.now())
    hours = 2
    return plot_data(start, hours)

@app.route('/plot-data/<start_date>/<start_time>/<hours>')
def plot_data(start_date, start_time, hours):
    '''return JSON data for given start_time and hours. '''
    # can't trust the user's start_time
    try:
        start_time = date_ui.to_rtime(start_date + " " + start_time)
    except ValueError:
        return (jsonify({'error': '''bad start time. use format YYYY-MM-DD HH:MM'''}), 400)
    try:
        hours = int(hours)
    except ValueError:
        return (jsonify({'error': '''bad duration. should be a positive integer like 2'''}), 400)
    # finally, real work
    conn = dbi.connect()
    data = ics.get_insulin_info(conn, start_time, hours)
    return jsonify(data)

@app.route ('/getRecentISF/<int:time_bucket>/<int:min_weeks>/<int:min_data>/')
def getRecentISF(time_bucket,min_weeks, min_data):
    '''Returns the first, second, and thrid quartile isf information given a time bucket and number of weeks and data points to look back. '''
    return_example_result = False
    if return_example_result:
        val = {'Q1': 4, 'Q2': 24, 'Q3': 48,
               'time_bucket': time_bucket,
               'weeks_of_data': 5,
               'number_of_data': 55,
               'min_number_of_data': min_data,
               'min_weeks_of_data': min_weeks,
               'timestamp_of_calculation': None}
    else:
        #get the number of weeks of data and isf data for recent ISF values 
        weeks_of_data, isf_vals = isf.getRecentISF(int(time_bucket),min_weeks,int( min_data))
        num_data = len(isf_vals)

        #calculate the index and value of first quartile 
        q1_index = ((num_data +1)/4)-1
        q1 = isf_vals[int(math.floor(q1_index))] + .5 * (isf_vals[int(math.ceil(q1_index))] - isf_vals[int(math.floor(q1_index))])

        #calculate the index and value of second quartile 
        q2_index = (((num_data +1)/4)-1) * 2
        q2 = isf_vals[int(math.floor(q2_index))] + .5 * (isf_vals[int(math.ceil(q2_index))] - isf_vals[int(math.floor(q2_index))])

        #calculate the index and value of third quartile 
        q3_index = (((num_data +1)/4)-1) * 3
        q3 = isf_vals[int(math.floor(q3_index))] + .5 * (isf_vals[int(math.ceil(q3_index))] - isf_vals[int(math.floor(q3_index))])

        current_time = datetime.now().strftime('%A, %d %B %Y')
    
        val = dict(Q1 = q1, Q2 = q2, Q3 = q3,
                   time_bucket = time_bucket,
                   weeks_of_data = weeks_of_data,
                   number_of_data = num_data,
                   min_number_of_data = min_data,
                   min_weeks_of_data = min_weeks,
                   timestamp_of_calculation = current_time)
    return jsonify(val)


@app.route('/isfplots/')
def isfplots():
    '''A box-and-whisker plot with isf data sorted in 2-hr time buckets '''
    return '''<p>sorry; this is not currently available; see Scott. 
             <p>The code was moved to the "outtakes/md_deploy.py" file.'''

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
