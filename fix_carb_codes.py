import os                       # for path.join
import sys
import math                     # for floor
import collections              # for deque
import cs304dbi as dbi
from datetime import datetime, timedelta
import date_ui
import logging

def fix_carb_codes(conn, rtime0, rtime1, debugp=True):
    if conn is None:
        conn = dbi.connect()
    curs = dbi.cursor(conn)
    rtime0 = date_ui.to_rtime(rtime0)
    rtime1 = date_ui.to_rtime(rtime1)
    logging.debug(f'searching for carbs from {rtime0} to {rtime1}')
    nrows = curs.execute('''select rtime, carbs
                            from janice.insulin_carb_smoothed_2
                            where carbs > 0 
                            and (carb_code is null or
                                 carb_code not in ('before6', 'breakfast', 'lunch', 'snack', 'dinner', 'after9', 'rescue'))
                            and %s <= rtime and rtime <= %s''',
                         [rtime0, rtime1])
    logging.debug(f'found {nrows} carbs to update')
    for row in curs.fetchall():
        (rtime, carbs) = row
        if matching_insulin_bolus(conn, rtime):
            carb_code = meal_name(rtime)
        else:
            carb_code = 'rescue'
        update = conn.cursor()
        logging.debug(f'{carbs} carbs at {str(rtime)} is {carb_code}')
        update.execute(f'''update {TABLE} 
                           set carbs = %s, carb_code = %s
                           where rtime = %s''',
                       [carbs, carb_code, rtime])
        if not debugp:
            conn.commit()
