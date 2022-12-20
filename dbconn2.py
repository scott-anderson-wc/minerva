#!/bin/env python2

'''Module to read MySQL database credentials and access databases as the MySQL user.

This module is designed to work with the MySQLdb package and make it
easier to read the database credentials from the standard ~/.my.cnf file,
or any file of similar format.  Doing so avoids putting those credentials
in the source code and removes that dependency from the code.

The format is a file of key = value pairs where the keys are host, user,
password and, optionally, database

Defines a read_cnf() function to return a dictionary with the MySQL
database credentials.

Also defines a function to replace the MySQL.connect function using a
dictionary of database credentials, as returned by the read_cnf()
function. That database connection is set to auto_commit().

In this module, DSN stands for "Data Source Name"

How to use this:

import MySQLdb
import dbconn2

Use one of the following to read the credentials (DSN) file

dsn = dbconn2.read_cnf()
dsn = dbconn2.read_cnf('~/.my.cnf')
dsn = dbconn2.read_cnf('/path/to/any/dsn_file')

Your credentials file may specify a database to connect to. You can
optionally assign or modify that value.

dsn['db'] = 'wmdb'     # the database we want to connect to

Use the DSN (credentials dictionary) to connect to the database. From here
on, use the MySQLdb API.

conn = dbconn2.connect(dsn)
curs = conn.cursor(MySQLdb.cursors.DictCursor) # results as Dictionaries
curs.execute('select name,birthdate from person')
curs.execute('select name,birthdate from person where name like %s',
             ['%george%'])
curs.fetchall()
curs.fetchone()
'''

import MySQLdb
import re
import os

def file_contents(filename):
    '''Returns contents of file as a string.'''
    with open(filename,"r") as infile:
        return infile.read()

def read_cnf(cnf_file=None):
    '''Read a file formatted like ~/.my.cnf file; defaulting to that
    file. Return a dictionary with the necessary information to connect to
    a database. See the connect() function.'''
    if cnf_file is None:
        cnf_file = os.path.expanduser('~/.my.cnf')
    else:
        cnf_file = os.path.expanduser(cnf_file)
    cnf = file_contents(cnf_file)
    credentials = {}
    # the key is the name used in the CNF file;
    # the value is the name used in the MySQLdb.connect() function
    mapping = {'host':'host',
               'user':'user',
               'password':'passwd',
               'database':'db'}
    for key in ('host', 'user', 'password', 'database' ):
        cred_key = mapping[key]
        regex = r"\b{k}\s*=\s*[\'\"]?(\w+)[\'\"]?\b".format(k=key)
        # print 'regex',regex
        p = re.compile(regex)
        m = p.search(cnf)
        if m:
            credentials[ cred_key ] = m.group(1)
        elif key == 'host' or key == 'database':
            credentials[ cred_key ] = 'not specified in ' + cnf_file
        else:
            raise Exception('Could not find key {k} in {f}'
                            .format(k=key,f=cnf_file))
    return credentials

def connect(dsn):
    '''Creates and returns a new database connection/handle given the dsn (a dictionary)

    The database connection is set to automatically commit.'''
    checkDSN(dsn)
    try:
        conn = MySQLdb.connect( use_unicode=True, charset='utf8', **dsn )
        # so each modification takes effect automatically
        conn.autocommit(True)
    except MySQLdb.Error as e:
        print(("Couldn't connect to database. MySQL error %d: %s" %
               (e.args[0], e.args[1])))
        raise
    return conn

def checkDSN(dsn):
    '''Raises a comprehensible error message if the DSN is missing some necessary info'''
    for key in ('host', 'user', 'passwd', 'db' ):
        if not key in dsn:
            raise KeyError('''DSN lacks necessary '{k}' key'''.format(k=key))
    return True

if __name__ == '__main__':
    print('starting test code')
    import sys
    if len(sys.argv) < 2:
        print(('''Usage: {cmd} cnf_file
test dbconn by giving the name of a cnf_file on the command line'''
              .format(cmd=sys.argv[0])))
        sys.exit(1)
    cnf_file = sys.argv[1]
    DSN = read_cnf(cnf_file)
    c = connect(DSN)
    print('successfully connected')
    curs = c.cursor(MySQLdb.cursors.DictCursor) # results as Dictionaries
    curs.execute('select user() as user, database() as db')
    row = curs.fetchone()
    print(('connected to {db} as {user}'
          .format(db=row['db'],user=row['user'])))
    # new for minervadiabetes
    curs.execute('select * from insulin_carb_smoothed_2')
    for row in curs.fetchall():
        print(row)

