'''Compute insulion on board (IOB) from insulin inputs and the insulin action curve.

'''

import MySQLdb
import dbconn2
import csv


def read_insulin_action_curve():
    with open('iac.csv', 'r') as csvfile:
        reader = csv.reader(csvfile, delimiter=',', quotechar='\'')
        return [ row for row in reader ]


            
