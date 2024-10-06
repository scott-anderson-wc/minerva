'''
Code for iterating over ICS2 and computing ranges of ISF values (clean and unclean regions)

The results are entered into the nudge_isfs_all table.

Author: Mileva
Created: 10/6/24
Last Updated: 10/6/24
'''

import logging
import sys
import MySQLdb
import dbconn2
import csv
import math
import itertools
from datetime import datetime, timedelta,date
import dateparser
import decimal     # some MySQL types are returned as type decimal
from dbi import get_dsn, get_conn # connect to the database
import date_ui
import numpy as np
import json
from typing import Optional
import pandas as pd
import argparse


from clean_nudge_isfs import compute_nudge_isfs, insert_isfs

MAPPING = [
    ("clean_5_min", 1,  False), 
    ("clean_15_min", 3,  False), 
    ("clean_30_min", 6,  False), 
    ("clean_2_hr", 24,  False), 
    ("clean_5_min_yrly_basal", 1,  True), 
    ("clean_15_min_yrly_basal", 3,  True), 
    ("clean_30_min_yrly_basal", 6,  True), 
    ("clean_2_hr_yrly_basal", 24,  True) 
]

## utils    
def get_latest_update_time(table: str) -> Optional[str]: 
    """ Obtain the most recent record in the given table"""
    curs.execute(f"select max(rtime) from {table}")
    last_update = curs.fetchone()[0]
    return last_update

def get_latest_records(min_date: Optional[str] = None): 
    """ Get the latest records from ICS2
    
    If min_date is provided, get all dates from the table after that time. 
    If min_date is not provided, get all records from the table. 
     
    """
    if min_date: 
        sql_statement = f"select rtime, cgm, dynamic_insulin from insulin_carb_smoothed_2 where rtime >= subtime(%s, '02:30:00')"
        curs.execute(sql_statement, [min_date])
    else: 
        sql_statement = f"select rtime, cgm, dynamic_insulin from insulin_carb_smoothed_2"
        curs.execute(sql_statement)
    
    return curs.fetchall()

## main script
def main_compute_all_nudge_isfs(table: str): 
    """ Main function to compute nudge ISFs over all rcords.""" 
    
    # Batch Update: Performs Nudge ISF computation for only the lastest records
    last_update = get_latest_update_time(table = table)
    latest_rows = get_latest_records(last_update)
    
    # Print statements
    print(f"{last_update=}")
    print(f"{len(latest_rows)=}")
    print(f"Inserting computations into {table=}")

    for column, window_length, yearly_basal in MAPPING: 
        print(f"\nwindow_length: {window_length}, column: {column}")
        
        nudge_isfs = compute_nudge_isfs(latest_rows, window_length = window_length, yearly_basal= yearly_basal)
        for i, (start_time, nudge_isf) in enumerate(nudge_isfs): 
            # print(f"i = {i} \t start_time = {start_time} \t nudge_isf = {nudge_isf}")
            insert_isfs(curs, rtime = start_time, isf = nudge_isf, column = column, table = table)
    
if __name__ == '__main__':
    
    parser = argparse.ArgumentParser(prog='Nudge ISFs', description='Compute and analyze nudge ISFs')
    parser.add_argument('-c', '--compute', action='store_true')
    parser.add_argument('-a', '--analyze', action='store_true')
    args = parser.parse_args()
    print(args)
    
    # configure_logging()
    conn = get_conn()
    curs = conn.cursor()
    
    if args.compute: 
        main_compute_all_nudge_isfs(table = "nudge_isf_results_avg")
    if args.analyze: 
        # main_analyze_nudge_isfs()
        pass
