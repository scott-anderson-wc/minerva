import os
from flask import (Flask, render_template, make_response, request, redirect, url_for,
                   session, flash, send_from_directory, g)
from flask import jsonify

import logging
import random
import math

LOGFILE='app.log'
LOGLEVEL=logging.DEBUG

from logging.handlers import RotatingFileHandler

from flask_mysqldb import MySQL
from datetime import datetime, timedelta
from dbi import get_dsn, get_conn # connect to the database
import food_graph

import json
import plotly
import plotly.plotly as py
import plotly.graph_objs as go

def debug(*args):
    s = ' '.join(map(str,args))
    if app.debug:
        print ("debug: "+s)
    else:
        app.logger.debug(s)

app = Flask(__name__)

# This sets the VERSION variable, among others.
# TODO: improve the protocol for using the database
app.config.from_object('config')
app.secret_key = os.urandom(24)
mysql = MySQL()
mysql.init_app(app)

color_with = 'rgb(31, 119, 180)'    # the default bluish color of 1st line
color_without = 'rgb(255, 127, 14)' # the default orangish color of 2nd line

def make_trace(times, trace, date, color):
    '''returns a dictionary with plotly info to create one line (trace) in a plot. 
the 'times' are the x values (strings like HH:MM) and the 'trace' is a list of
cgm value (integers). date is a date object for the date of the trace. 
'color' is a plotly/css color spec like rgb(31, 119, 180)
'''
    print('in make_trace: {} {}'.format(date,type(date)))
    d = date.strftime('%m/%d/%Y')
    dt = {'x': times, 'y': trace, 'mode': 'lines', 'name': d,
          'line': { 'color': color, 'width': 1, 'dash': 'dash'}}
    return dt

@app.route('/avgBG/')
def average_bg():
    hours = 3
    duration = hours*60         # minutes
    layout = go.Layout( title = 'Average BG Post Meal {} Hours '.format(hours),
                        yaxis = dict(title='BG Value',
                                     # the y zeroline is the line where y=0
                                     zeroline=True,
                                     zerolinecolor='#800000',
                                     zerolinewidth=2,
                                     # this is the vertical line at the left edge
                                     showline=False,
                                     rangemode='tozero'),
                        xaxis = dict(title='Minutes Post Meal (Dinner)',
                                     showline=True,
                                     zeroline=True,
                                     tickangle=45
                                     )
                      
                        )
    traces = []
    times = list(range(0,duration+5,5))
    DATA_FOOD, DATA_NO_FOOD, traces_with, traces_without, dates_with, dates_without = food_graph.post_meal_cgm_traces_between_dates(
        '2016-04-02', '2016-05-03', 'dinner', duration,
        ['avocado'], [])
    print('in md, dates_with')
    print([(d,type(d)) for d in dates_with])
    print('in md, dates_without')
    print([(d,type(d)) for d in dates_without])
    data_trace_with = { 'x': times, 'y': DATA_FOOD, 'mode': 'lines',
                        'name': 'With Avocado',
                        'line': { 'color': color_with, 'width': 3 } };
    data_trace_without = { 'x': times, 'y': DATA_NO_FOOD, 'mode': 'lines',
                           'name': 'Without Avocado',
                           'line': { 'color': color_without, 'width': 3 } };
    traces.append(data_trace_with)
    traces.append(data_trace_without)
    for trace,date in zip(traces_with, dates_with):
        traces.append(make_trace(times,trace,date,color_with))
    for trace,date in zip(traces_without, dates_without):
        traces.append(make_trace(times,trace,date,color_without))
        
    minimum_bg = go.Scatter(x=times, y=[80]*len(DATA_FOOD), name="Minimum Ideal BG Value",
                            line={'color': 'rgb(255,0,0)'})
    maximum_bg = go.Scatter(x=times, y=[120]*len(DATA_FOOD), name="Maximum Ideal BG Value",
                            line={'color': 'rgb(0,128,0)'})
    traces.append(minimum_bg)
    traces.append(maximum_bg)
    graph = go.Figure(data = traces, layout = layout)
    graphJSON = json.dumps( graph, cls=plotly.utils.PlotlyJSONEncoder)
    print('in avgBG, about to render template')
    return render_template('meal_traces.html',
                           version = app.config['VERSION'],
                           page_title='Minerva',
                           graphJSON = graphJSON)


if __name__ == '__main__':
    port = 1943
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
