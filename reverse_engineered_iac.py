import os
from flask import (Flask, render_template, url_for, request)

import MySQLdb
from flask_mysqldb import MySQL
from datetime import datetime, timedelta
from dbi import get_dsn, get_conn # connect to the database
from datetime import date

import json
import csv

import pandas as pd
import numpy as np

from cleanregions import get_clean_regions_5hr

#==========================================================================================================================================
# Helper functions

def clean_regions(conn):
    '''Returns 5hr clean regions (rtime only) used by app.py. Omits regions where bg increases despite bolus'''
    curs = conn.cursor(MySQLdb.cursors.DictCursor)
    curs.execute('''select rtime
                    from clean_regions_5hr
                    where bg0 > bg1''')
    regions = curs.fetchall()
    print(len(regions))
    return regions


def valid_clean_regions(conn):
    '''Returns 5hr clean regions (rtime, bg0, bg1, and bolus) used to create plotly traces. Omits regions where bg increases despite bolus'''
    curs = conn.cursor(MySQLdb.cursors.DictCursor)
    curs.execute('''select rtime, bg0, bg1, bolus
                    from clean_regions_5hr
                    where bg0 > bg1''')
    regions = curs.fetchall()
    return regions

#==========================================================================================================================================
# Compute and export reverse engineered IAC

def reverse_engineered_5hr_iac(conn):
    '''Computes the reverse engineered iac using
    1. the equation 5_min_delta_cgm/ total_bolus
    2. the 5-hr clean regions from the clean_regions_5hr table (omitting all cases where CGM decreases)
    '''
    print("--------------Reverse Engineer 5hr IAC--------------")
    clean_regions = valid_clean_regions(conn)

    iacs = {}
    # For each 5hr clean region
    for row in clean_regions:
        start_time, bg_start, bg_end, bolus = row['rtime'], row['bg0'], row['bg1'], row['bolus']
        iacs[start_time] = [] # Store delta_standards for each 5hr trace
        skipped_null = 0 # Number of cases with null cgm values

        # Data for every 5_min_increment within 5hr region
        curs = conn.cursor()
        curs.execute('''select rtime, cgm, bg
                    from insulin_carb_smoothed_2
                    where rtime >= %s and rtime <= addtime(%s, '5:00')''',
                    [start_time, start_time])
        rows = curs.fetchall()

        # COMPUTE delta standards
        for i in range(len(rows) - 1):
            rtime_now, cgm_now, bg_now = rows[i]
            rtime_next, cgm_next, bg_next = rows[i+1]

            ## Use cgm to compute delta_standard
            if cgm_now and cgm_next:
                delta_standard = float(cgm_next - cgm_now)/ float(bolus)
            else:
                skipped_null += 1
                delta_standard = None

            ## Store delta standard
            iacs[start_time].append(delta_standard)

    all_traces = [iacs[key] for key in iacs] # list of all the delta_standard traces as (n x 60 matrix)
    delta_standards_by_increments = zip(*all_traces) # zip delta standards for first 5 min, for next 5 min, ..., for last 5 min

    # Compute IAC, obtain avg and std. dev. for each 5 min increment
    iac = []
    errors = []
    for inc_5_min in delta_standards_by_increments:
        inc_5_min = [val for val in inc_5_min if val is not None]
        iac.append(np.mean(inc_5_min))
        errors.append(np.std(inc_5_min))

    # Create IAC
    iac = [-val for val in iac]
    times = np.linspace(0, 259, 60)

    return iac


def export_5hr_IAC_to_CSV(iac):
    ''' Exports the 5-hr reverse engineered IAC to a csv file '''

    print("--------------Exporting 5hr IAC to CSV --------------")

    # First column: Time from 0-300 in 5 minute increments
    # Second column: Corresponding value of the IAC curve
    row_headers = ["Time", "IAC"]
    times = np.linspace(0, 295, 60).astype(int)

    # Export IAC to csv file
    filepath = "reverse_engineered_iac_{}.csv".format(date.today())
    file = open(filepath, "w")
    writer = csv.writer(file)

    writer.writerow(row_headers)
    for i in range(0, len(times)):
        writer.writerow([times[i], iac[i]])
    file.close()
    print(f"Successfully wrote to {filepath}")


if __name__ == "__main__":
    get_clean_regions_5hr()
    conn = get_conn()
    # print(make_iac_trace_bolus(conn,"2014-03-23 04:05:00"))
    # findFlippedTraces()
    # get_clean_regions(conn)
    # get_IAC_totaldelta_by_year(conn)
    iac = reverse_engineered_5hr_iac(conn)
    export_5hr_IAC_to_CSV(iac)

