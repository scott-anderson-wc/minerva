'''March 2022.

Segun has created a web API for the Diamond data that
makes the rescue carbs available at

http://minervaanalysis.net/analytics/userCarbs?fromTimestamp=2022-01-02T13:56:55&userId=4

We want to copy that data over to the Janice database so that we can
include them in our predictive model.

That data looks like:

{"timestamp":"2022-01-02T22:23:15.000Z",
   "carbName":"Juice box",
   "quantity":1,
   "carbCountGrams":15,
   "totalCarbGrams":15,
   "userId":4}

This Python script uses the requests module and pymysql to pull the
data from Segun's web API and put it into the
rescue_carbs_from_diamond table, defined in 

sql/rescue_carbs_from_diamond.sql

Eventually, this script will be run by cron every 5 minutes. That's
probably too often, but if the load isn't bad, maybe it's okay. 

The script should keep track of when it was last run. It'll do that
using the contents of

/home/hugh9/last_pull_data_from_diamond.log

Scott D. Anderson
March 24, 2022

'''

import os
import requests
import cs304dbi as dbi
from datetime import datetime

DIAMOND = 'http://minervaanalysis.net/analytics/userCarbs'
SINCE_FILE = '/home/hugh9/last_pull_data_from_diamond.log'
ISO_FMT = '%Y-%m-%dT%H:%M:%S'

def get_data(fromTimestamp, userId=4):
    resp = requests.get(DIAMOND, {'fromTimestamp': fromTimestamp, 'userId': userId})
    return resp.json()

def convert_timestamp(timestr):
    return datetime.strptime(timestr,ISO_FMT+'.%fZ').strftime(ISO_FMT)

def store_data(conn, data):
    curs = dbi.cursor(conn)
    for row in data:
        userId, timestamp, carbCountGrams, totalCarbGrams, quantity, carbName = (
            row['userId'],
            row['timestamp'],
            row['carbCountGrams'],
            row['totalCarbGrams'],
            row['quantity'],
            row['carbName'])
        timestamp = convert_timestamp(timestamp)
        # note that, currently, the key is timestamp only, because we only have one user
        curs.execute('''insert into rescue_carbs_from_diamond
                        (user, timestamp, carbCountGrams, totalCarbGrams, quantity, carbName)
                        values (%s, %s, %s, %s, %s, %s)
                        on duplicate key update
                        carbCountGrams = %s, totalCarbGrams = %s, quantity = %s, carbName = %s;''',
                     [userId, timestamp, carbCountGrams, totalCarbGrams, quantity, carbName,
                      carbCountGrams, totalCarbGrams, quantity, carbName ])
    conn.commit()

def find_since():
    with open(SINCE_FILE, 'r') as fin:
        since_str = fin.read()
    return since_str, datetime.strptime(since_str, ISO_FMT)

def store_time(timestamp=None):
    if timestamp is None:
        timestamp = datetime.now().strftime(ISO_FMT)
    with open(SINCE_FILE, 'w') as fout:
        fout.write(timestamp)

def transfer(since_str=None):
    if since_str is None:
        since_str = find_since()
    data = get_data(since_str)
    if len(data) > 0:
        dbi.cache_cnf()
        conn = dbi.connect()
        store_data(conn, data)
    store_time()

if __name__ == '__main__':
    transfer()
    
