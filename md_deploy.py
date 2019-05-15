import os, sys
from flask import (Flask, render_template, make_response, request, redirect, url_for,
                   session, flash, send_from_directory, g)
from flask import jsonify
from werkzeug import secure_filename

import time
import logging
import random
import math

'''Deployed app'''

LOGFILE='md_deploy.log'
LOGLEVEL=logging.DEBUG

from logging.handlers import RotatingFileHandler

from flask_mysqldb import MySQL
from datetime import datetime, timedelta
import db
from dbi import get_dsn, get_conn # connect to the database
import isf2 as isf
import date_ui

import json
import plotly
import plotly.plotly as py
import plotly.graph_objs as go

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

@app.route('/info')
def info():
    '''Info about the app deployment'''
    flash('Python version is {}'.format(sys.version))
    for p in sys.path:
        flash('Path has {}'.format(p))
    return render_template('b.html')


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

        #calculae the index and value of first quartile 
        q1_index = ((num_data +1)/4)-1
        q1 = isf_vals[int(math.floor(q1_index))] + .5 * (isf_vals[int(math.ceil(q1_index))] - isf_vals[int(math.floor(q1_index))])

        #calcilate the index and value of second quartile 
        q2_index = (((num_data +1)/4)-1) * 2
        q2 = isf_vals[int(math.floor(q2_index))] + .5 * (isf_vals[int(math.ceil(q2_index))] - isf_vals[int(math.floor(q2_index))])

        #calcularte the index and value of third quartile 
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


@app.route('/isfcompareYears/')
def isf_compare_year():
    #get data for each year
    (all_2014, bucket_list_2014) = isf.get_isf_for_years('2014', '2014')
    (all_2015, bucket_list_2015) = isf.get_isf_for_years('2015', '2015')
    (all_2016, bucket_list_2016) = isf.get_isf_for_years('2016', '2016')
    (all_2017, bucket_list_2017) = isf.get_isf_for_years('2017', '2017')
    (all_2018, bucket_list_2018) = isf.get_isf_for_years('2018', '2018')

    #get non-bucketed data for each year
    allData_2014 = [data[0] for data in all_2014 if data[0]]
    allData_2015 = [data[0] for data in all_2015 if data[0]]
    allData_2016 = [data[0] for data in all_2016 if data[0]]
    allData_2017 = [data[0] for data in all_2017 if data[0]]
    allData_2018 = [data[0] for data in all_2018 if data[0]]

    #layout dict
    yaxis_dict = dict(title = 'mgdl/unit',
                      zeroline = True,
                      zerolinecolor = '#800000',
                      showline = False,
                      rangemode = 'tozero')

    #create plot for non-bucketed data
    allWhisker_2014 = go.Box(y = allData_2014,name = '2014')
    allWhisker_2015 = go.Box(y = allData_2015,name = '2015')
    allWhisker_2016 = go.Box(y = allData_2016,name = '2016')
    allWhisker_2017 = go.Box(y = allData_2017,name = '2017')
    allWhisker_2018 = go.Box(y = allData_2018,name = '2018')
    layout_allWhisker = go.Layout(title = ('All ISF values for each yaer'), width = 1000, height = 800,
                                  yaxis = yaxis_dict)
    graph_all = go.Figure(data = [allWhisker_2014, allWhisker_2015,allWhisker_2016,allWhisker_2017,allWhisker_2018], layout = layout_allWhisker)
    graphJSON_all = json.dumps(graph_all, cls= plotly.utils.PlotlyJSONEncoder)

    #create plot for 0-2am time bucket
    plot14_0 = go.Box(y = bucket_list_2014[0], name = '2014')
    plot15_0 = go.Box(y = bucket_list_2015[0], name = '2015')
    plot16_0 = go.Box(y = bucket_list_2016[0], name = '2016')
    plot17_0 = go.Box(y = bucket_list_2017[0], name = '2017')
    plot18_0 = go.Box(y = bucket_list_2018[0], name = '2018')
    layout_0am = go.Layout(title = ('ISF values for 0am-2am time bucket'), width = 1000,height = 800,
                           yaxis=yaxis_dict)
    graph_0am = go.Figure(data = [plot14_0,plot15_0,plot16_0,plot17_0,plot18_0], layout=layout_0am)
    graphJSON_0am = json.dumps(graph_0am,cls= plotly.utils.PlotlyJSONEncoder)

    #create plot for 2-4am time bucket
    plot14_1 = go.Box(y = bucket_list_2014[1], name = '2014')
    plot15_1 = go.Box(y = bucket_list_2015[1], name = '2015')
    plot16_1 = go.Box(y = bucket_list_2016[1], name = '2016')
    plot17_1 = go.Box(y = bucket_list_2017[1], name = '2017')
    plot18_1 = go.Box(y = bucket_list_2018[1], name = '2018')
    layout_2am = go.Layout(title = ('ISF values for 2am-4am time bucket'), width = 1000,height = 800,
                           yaxis=yaxis_dict)
    graph_2am = go.Figure(data = [plot14_1,plot15_1,plot16_1,plot17_1,plot18_1], layout=layout_2am)
    graphJSON_2am = json.dumps(graph_2am,cls= plotly.utils.PlotlyJSONEncoder)

    #create plot for 4-6am time bucket
    plot14_2 = go.Box(y = bucket_list_2014[2], name = '2014')
    plot15_2 = go.Box(y = bucket_list_2015[2], name = '2015')
    plot16_2 = go.Box(y = bucket_list_2016[2], name = '2016')
    plot17_2 = go.Box(y = bucket_list_2017[2], name = '2017')
    plot18_2 = go.Box(y = bucket_list_2018[2], name = '2018')
    layout_4am = go.Layout(title = ('ISF values for 4am-6am time bucket'), width = 1000,height = 800,
                           yaxis=yaxis_dict)
    graph_4am = go.Figure(data = [plot14_2,plot15_2,plot16_2,plot17_2,plot18_2], layout=layout_4am)
    graphJSON_4am = json.dumps(graph_4am,cls= plotly.utils.PlotlyJSONEncoder)

    #create plot for 6am-8am time bucket
    plot14_3 = go.Box(y = bucket_list_2014[3], name = '2014')
    plot15_3 = go.Box(y = bucket_list_2015[3], name = '2015')
    plot16_3 = go.Box(y = bucket_list_2016[3], name = '2016')
    plot17_3 = go.Box(y = bucket_list_2017[3], name = '2017')
    plot18_3 = go.Box(y = bucket_list_2018[3], name = '2018')

    layout_6am = go.Layout(title = ('ISF values for 6am-8am time bucket'), width = 1000,height = 800,
                           yaxis=yaxis_dict)

    graph_6am = go.Figure(data = [plot14_3,plot15_3,plot16_3,plot17_3,plot18_3], layout=layout_6am)
    graphJSON_6am = json.dumps(graph_6am,cls= plotly.utils.PlotlyJSONEncoder)

    #create plot for 8am-10am time bucket
    plot14_4 = go.Box(y = bucket_list_2014[4], name = '2014')
    plot15_4 = go.Box(y = bucket_list_2015[4], name = '2015')
    plot16_4 = go.Box(y = bucket_list_2016[4], name = '2016')
    plot17_4 = go.Box(y = bucket_list_2017[4], name = '2017')
    plot18_4 = go.Box(y = bucket_list_2018[4], name = '2018')

    layout_8am = go.Layout(title = ('ISF values for 8am-10am time bucket'), width = 1000,height = 800,
                            yaxis=yaxis_dict)

    graph_8am = go.Figure(data = [plot14_4,plot15_4,plot16_4,plot17_4,plot18_4], layout=layout_8am)
    graphJSON_8am = json.dumps(graph_8am,cls= plotly.utils.PlotlyJSONEncoder)

    #create plot for 10am-12pm time bucket
    plot14_5 = go.Box(y = bucket_list_2014[5], name = '2014')
    plot15_5 = go.Box(y = bucket_list_2015[5], name = '2015')
    plot16_5 = go.Box(y = bucket_list_2016[5], name = '2016')
    plot17_5 = go.Box(y = bucket_list_2017[5], name = '2017')
    plot18_5 = go.Box(y = bucket_list_2018[5], name = '2018')

    layout_10am = go.Layout(title = ('ISF values for 10am-12pm time bucket'), width = 1000,height = 800,
                            yaxis=yaxis_dict)
    graph_10am = go.Figure(data = [plot14_5,plot15_5,plot16_5,plot17_5,plot18_5], layout=layout_10am)
    graphJSON_10am = json.dumps(graph_10am,cls= plotly.utils.PlotlyJSONEncoder)

    #create plot for 12pm-2pm time bucket
    plot14_6 = go.Box(y = bucket_list_2014[6], name = '2014')
    plot15_6 = go.Box(y = bucket_list_2015[6], name = '2015')
    plot16_6 = go.Box(y = bucket_list_2016[6], name = '2016')
    plot17_6 = go.Box(y = bucket_list_2017[6], name = '2017')
    plot18_6 = go.Box(y = bucket_list_2018[6], name = '2018')

    layout_12pm = go.Layout(title = ('ISF values for 12pm-2pm time bucket'), width = 1000,height = 800,
                            yaxis=yaxis_dict)
    graph_12pm = go.Figure(data = [plot14_6,plot15_6,plot16_6,plot17_6,plot18_6], layout=layout_12pm)
    graphJSON_12pm = json.dumps(graph_12pm,cls= plotly.utils.PlotlyJSONEncoder)

    #create plot for 2pm-4pm time bucket
    plot14_7 = go.Box(y = bucket_list_2014[7], name = '2014')
    plot15_7 = go.Box(y = bucket_list_2015[7], name = '2015')
    plot16_7 = go.Box(y = bucket_list_2016[7], name = '2016')
    plot17_7 = go.Box(y = bucket_list_2017[7], name = '2017')
    plot18_7 = go.Box(y = bucket_list_2018[7], name = '2018')

    layout_2pm = go.Layout(title = ('ISF values for 2pm-4pm time bucket'), width = 1000,height = 800,
                           yaxis=yaxis_dict)
    graph_2pm = go.Figure(data = [plot14_7,plot15_7,plot16_7,plot17_7,plot18_7], layout=layout_2pm)
    graphJSON_2pm = json.dumps(graph_2pm,cls= plotly.utils.PlotlyJSONEncoder)
         

    #create plot for 4pm-6pm time bucket
    plot14_8 = go.Box(y = bucket_list_2014[8], name = '2014')
    plot15_8 = go.Box(y = bucket_list_2015[8], name = '2015')
    plot16_8 = go.Box(y = bucket_list_2016[8], name = '2016')
    plot17_8 = go.Box(y = bucket_list_2017[8], name = '2017')
    plot18_8 = go.Box(y = bucket_list_2018[8], name = '2018')

    layout_4pm = go.Layout(title = ('ISF values for 4pm-6pm time bucket'), width = 1000,height = 800,
                            yaxis=yaxis_dict)
    graph_4pm = go.Figure(data = [plot14_8,plot15_8,plot16_8,plot17_8,plot18_8], layout=layout_4pm)
    graphJSON_4pm = json.dumps(graph_4pm,cls= plotly.utils.PlotlyJSONEncoder)

    #create plot for 6pm-8pm time bucket
    plot14_9 = go.Box(y = bucket_list_2014[9], name = '2014')
    plot15_9 = go.Box(y = bucket_list_2015[9], name = '2015')
    plot16_9 = go.Box(y = bucket_list_2016[9], name = '2016')
    plot17_9 = go.Box(y = bucket_list_2017[9], name = '2017')
    plot18_9 = go.Box(y = bucket_list_2018[9], name = '2018')

    layout_6pm = go.Layout(title = ('ISF values for 6pm-8pm time bucket'), width = 1000,height = 800,
                            yaxis=yaxis_dict)
    graph_6pm = go.Figure(data = [plot14_9,plot15_9,plot16_9,plot17_9,plot18_9], layout=layout_6pm)
    graphJSON_6pm = json.dumps(graph_6pm,cls= plotly.utils.PlotlyJSONEncoder)

    #create plot for 8pm-10pm time bucket
    plot14_10 = go.Box(y = bucket_list_2014[10], name = '2014')
    plot15_10 = go.Box(y = bucket_list_2015[10], name = '2015')
    plot16_10 = go.Box(y = bucket_list_2016[10], name = '2016')
    plot17_10 = go.Box(y = bucket_list_2017[10], name = '2017')
    plot18_10 = go.Box(y = bucket_list_2018[10], name = '2018')

    layout_8pm = go.Layout(title = ('ISF values for 8pm-10pm time bucket'), width = 1000,height = 800,
                            yaxis=yaxis_dict)
    graph_8pm = go.Figure(data = [plot14_10,plot15_10,plot16_10,plot17_10,plot18_10], layout=layout_8pm)
    graphJSON_8pm = json.dumps(graph_8pm,cls= plotly.utils.PlotlyJSONEncoder)

    #create plot for 10pm-12am time bucket
    plot14_11 = go.Box(y = bucket_list_2014[11], name = '2014')
    plot15_11 = go.Box(y = bucket_list_2015[11], name = '2015')
    plot16_11 = go.Box(y = bucket_list_2016[11], name = '2016')
    plot17_11 = go.Box(y = bucket_list_2017[11], name = '2017')
    plot18_11 = go.Box(y = bucket_list_2018[11], name = '2018')

    layout_10pm = go.Layout(title = ('ISF values for 10pm-12am time bucket'), width = 1000,height = 800,
                           yaxis=yaxis_dict)
    graph_10pm = go.Figure(data = [plot14_11,plot15_11,plot16_11,plot17_11,plot18_11], layout=layout_10pm)
    graphJSON_10pm = json.dumps(graph_10pm,cls= plotly.utils.PlotlyJSONEncoder)
        
    return render_template('isfYear.html',
                           version = app.config['VERSION'],
                           page_title = 'Minerva Compare ISF Values',
                           graphJSON_all = graphJSON_all,
                           graphJSON_0am = graphJSON_0am,
                           graphJSON_2am = graphJSON_2am,
                           graphJSON_4am = graphJSON_4am,
                           graphJSON_6am = graphJSON_6am,
                           graphJSON_8am = graphJSON_8am,
                           graphJSON_10am = graphJSON_10am,
                           graphJSON_12pm = graphJSON_12pm,
                           graphJSON_2pm = graphJSON_2pm,
                           graphJSON_4pm = graphJSON_4pm,
                           graphJSON_6pm = graphJSON_6pm,
                           graphJSON_8pm = graphJSON_8pm,
                           graphJSON_10pm = graphJSON_10pm)


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
