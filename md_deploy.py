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

@app.route('/displayRecentISF')
def displayRecentISF():
    '''This just displays the page; all the data is gotten by Ajax. See below.'''
    return render_template('isf-display.html')

@app.route('/getRecentISF/<int:bucket>/<int:weeks>/<int:min_data>/')
def getRecentISF(bucket,weeks,min_data):
    val = {'Q1': 4, 'Q2': 24, 'Q3': 48,
           time_bucket: bucket,
           weeks_of_data: weeks,
           number_of_data: 55,
           min_number_of_data: min_data,
           timestamp_of_calculation: None}
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

    (all_before, bucket_list_before) = isf.get_isf_for_years('2014','2016')
    all_before_data = [data[0] for data in all_before if data[0]]

    all_before_whisker = go.Box(y = all_before_data, name = 'all isf 2014-2016')
    bucket14_1 = go.Box(y = bucket_list_before[0], name = '0am-2am')
    bucket14_2 = go.Box(y = bucket_list_before[1], name ='2am-4am')
    bucket14_3 = go.Box(y = bucket_list_before[2], name = '4am-6am')
    bucket14_4 = go.Box(y = bucket_list_before[3], name = '6am-8am')
    bucket14_5 = go.Box(y = bucket_list_before[4], name = '8am-10am')
    bucket14_6 = go.Box(y = bucket_list_before[5], name = '10am-12pm')
    bucket14_7 = go.Box(y = bucket_list_before[6], name = '12pm-14pm')
    bucket14_8 = go.Box(y = bucket_list_before[7], name = '14pm-16pm')
    bucket14_9 = go.Box(y = bucket_list_before[8], name = '16pm-18pm')
    bucket14_10 = go.Box(y = bucket_list_before[9], name = '18pm-20pm')
    bucket14_11 = go.Box(y = bucket_list_before[10], name = '20pm-22pm')
    bucket14_12 = go.Box(y = bucket_list_before[11], name = '22pm-24am')
    
    layout2 = go.Layout(title = ('isf values from 2014-2016'), width=1500, height= 1000,
                       yaxis = dict(title='mgdl/unit',
                                    zeroline = True,
                                    zerolinecolor='#800000',
                                    zerolinewidth = 2,
                                    showline =False,
                                    rangemode='tozero')
                       )
    graph_before = go.Figure(data = [all_before_whisker,bucket14_1,bucket14_2,bucket14_3,bucket14_4,bucket14_5,bucket14_6,bucket14_7,bucket14_8,bucket14_9,bucket14_10,bucket14_11,bucket14_12],layout=layout2)
    graphJSON2 = json.dumps(graph_before, cls=plotly.utils.PlotlyJSONEncoder)

    (all_after, bucket_list_after) = isf.get_isf_for_years('2016','2018')
    all_after_data = [data[0] for data in all_after if data[0]]
    
    all_after_whisker = go.Box(y = all_after_data, name = 'all isf 2016-2018')
    bucket16_1 = go.Box(y = bucket_list_after[0], name = '0am-2am')
    bucket16_2 = go.Box(y = bucket_list_after[1], name = '2am-4am')
    bucket16_3 = go.Box(y = bucket_list_after[2], name = '4am-6am')
    bucket16_4 = go.Box(y = bucket_list_after[3], name = '6am-8am')
    bucket16_5 = go.Box(y = bucket_list_after[4], name = '8am-10am')
    bucket16_6 = go.Box(y = bucket_list_after[5], name = '10am-12pm')
    bucket16_7 = go.Box(y = bucket_list_after[6], name = '12pm-14pm')
    bucket16_8 = go.Box(y = bucket_list_after[7], name = '14pm-16pm')
    bucket16_9 = go.Box(y = bucket_list_after[8], name = '16pm-18pm')
    bucket16_10 = go.Box(y= bucket_list_after[9], name = '18pm-20pm')
    bucket16_11 = go.Box(y = bucket_list_after[10], name = '20pm-22pm')
    bucket16_12 = go.Box(y = bucket_list_after[11], name = '22pm-24pm')
    
    layout3 = go.Layout(title = ('isf vales from 2016-2018'), width = 1500, height = 1000,
                        yaxis = dict(title = 'mgdl/unit',
                                     zeroline = True,
                                     zerolinecolor = '#800000',
                                     zerolinewidth = 2,
                                     showline = False,
                                     rangemode = 'tozero')
                        )

    graph_after = go.Figure(data = [all_after_whisker, bucket16_1,bucket16_2,bucket16_3,bucket16_4,bucket16_5,bucket16_6,bucket16_7,bucket16_8,bucket16_9,bucket16_10,bucket16_11,bucket16_12], layout = layout3)
    graphJSON3 = json.dumps(graph_after, cls=plotly.utils.PlotlyJSONEncoder)

    isf.get_tvalue() 
    return render_template('isfplots.html',
                           version = app.config['VERSION'],
                           page_title='Minerva ISF values',
                           graphJSON = graphJSON,
                           graphJSON2 = graphJSON2,
                           graphJSON3= graphJSON3)


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
