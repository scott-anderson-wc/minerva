'''Janice wanted CGM curves for Breakfast, Lunch and Dinner for 2 months

I'm going to search for meals over two months, then select rtime, cgm
for 3 hours post-meal.

I'm also going to derive a time_of_day and time_since_meal so that
they can be easily compared.

November 11, 2021

'''

import sys
import math
import logging
from datetime import datetime, timedelta
import json
import config
import cs304dbi as dbi
import date_ui
import random
import csv

def find_meals(conn, start_date, end_date):
    # start_date = date_ui.to_datetime(start_date)
    # end_date = date_ui.to_datetime(end_date)
    curs = dbi.dict_cursor(conn)
    curs.execute('''select carb_code, rtime from insulin_carb_smoothed_2
                    where carb_code in ('breakfast', 'lunch', 'dinner') and
                    %s < rtime and rtime < %s''',
                 [start_date, end_date])
    desc = 'meals-between-{}-and-{}.csv'.format(start_date, end_date)
    with open(desc, 'w', newline='') as csvfile:
        mealwriter = csv.DictWriter(csvfile, 
                                    dialect = 'excel-tab',
                                    fieldnames=('carb_code','rtime'),
                                    quoting=csv.QUOTE_MINIMAL)
        mealwriter.writeheader()
        for row in curs.fetchall():
            mealwriter.writerow(row)
            cgm_curve(conn, row['carb_code'], row['rtime'])

def cgm_curve(conn, carb_code, rtime):
    date = date_ui.to_datetime(rtime)
    desc = 'cgm-curve-{meal}-on-{date}.csv'.format(meal = carb_code,
                                                   date = date.strftime('%Y-%m-%d'))
    curs = dbi.dict_cursor(conn)
    curs.execute('''SELECT rtime, minutes_since_last_meal, cgm 
                    FROM insulin_carb_smoothed_2
                    WHERE %s < rtime and rtime < %s''',
                 [date, date + timedelta(hours=3)])
    with open(desc, 'w', newline='') as csvfile:
        mealwriter = csv.DictWriter(csvfile,
                                    dialect = 'excel-tab',
                                    fieldnames=('rtime', 'minutes_since_last_meal', 'cgm'),
                                    quoting=csv.QUOTE_MINIMAL)
        mealwriter.writeheader()
        for row in curs.fetchall():
            mealwriter.writerow(row)
    

if __name__ == '__main__':
    if sys.argv[1] == 'dialects':
        print(csv.list_dialects())

    dbi.cache_cnf()
    conn = dbi.connect()

    if sys.argv[1] == 'meals':
        find_meals(conn, sys.argv[2], sys.argv[3])
        
    if sys.argv[1] == 'cgm':
        cgm_curve(conn, sys.argv[2], sys.argv[3])
        
