'''Compute Mina's 2hr ISFs based on 2hr clean regions.

Author: Mileva
Last Updated: 7/28/24
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

def get_clean_isfs(curs) -> list:
    ''' Returns all 2hr Clean ISFs '''
    curs.execute('''SELECT rtime, isf from clean_regions_2hr_new;''')
    clean_isfs = curs.fetchall()
    return clean_isfs
    
def get_clean_isfs_df(curs) -> pd.DataFrame: 
    ''' Returns a dataframe of all 2hr Clean ISFs'''
    clean_isfs = get_clean_isfs(curs)
   
    # convert lst_of_tuples to lst_of_lst
    clean_isfs = [list(tple) for tple in clean_isfs]
    df = pd.DataFrame(clean_isfs, columns = ["rtime", "isf"])
    df["rtime"] = pd.to_datetime(df["rtime"])
    df["hour"] = df["rtime"].hour
    df["year"] = df["rtime"].year
    
    print(df)
    print(df.types)
    
if __name__ == '__main__':
    
    conn = get_conn()
    curs = conn.cursor()
    
    get_clean_isfs_df()
