import os
from flask import (Flask, render_template, make_response, request, redirect, url_for,
                   session, flash, send_from_directory, g)
from flask import jsonify
from werkzeug import secure_filename

import time
import logging
import random
import math

LOGFILE='md_deploy.log'
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

@app.route('/')
def displayRecentISF():
    '''This just displays the page; all the data is gotten by Ajax. See below.'''
    return render_template('isf-display.html')

@app.route ('/getRecentISF/<int:time_bucket>/<int:min_weeks>/<int:min_data>/')
def getRecentISF(time_bucket,min_weeks, min_data):
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
        weeks_of_data, isf_vals = isf.getRecentISF(int(time_bucket),min_weeks,int( min_data))
        num_data = len(isf_vals)
    
        q1_index = ((num_data +1)/4)-1
        q1 = isf_vals[int(math.floor(q1_index))] + .5 * (isf_vals[int(math.ceil(q1_index)) - int(math.floor(q1_index))])

        q2_index = (((num_data +1)/4)-1) * 2
        q2 = isf_vals[int(math.floor(q2_index))] + .5 * (isf_vals[int(math.ceil(q2_index)) - int(math.floor(q2_index))])

        q3_index = (((num_data +1)/4)-1) * 3
        q3 = isf_vals[int(math.floor(q3_index))] + .5 * (isf_vals[int(math.ceil(q3_index)) - int(math.floor(q3_index))])

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
    (all, bucket_list) = isf.get_all_isf_plus_buckets()
    allData = [data[0] for data in all if data[0]]

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
