'''Module to read MySQL database credentials and access databases as the
MySQL user.

This module works with PyMySQL and Python3!

This module is designed to work with the pymysql package and make it
easier to read the database credentials from the standard ~/.my.cnf file,
or any file of similar format.  Doing so avoids putting those credentials
in the source code and removes that dependency from the code.

The format is a file of key = value pairs where the keys are host, user,
password and, optionally, database

Defines a read_cnf() function to return a dictionary with the MySQL
database credentials.

Defines a cache_cnf() function to do the same thing, but only read the
file once, caching the database credentials.

Also defines a function to replace the pymysql.connect function using a
dictionary of database credentials, as returned by the read_cnf()
function.

That database connection is set to auto_commit(), but you can modify that
by using the conn.autocommit() method on the database connection:

conn=connect(dsn)
conn.autocommit(False)

In this module, DSN stands for "Data Source Name"

How to use this:

import cs304dbi as dbi

Use one of the following to read the credentials (DSN) file

dsn = dbi.read_cnf()
dsn = dbi.read_cnf('~/.my.cnf')
dsn = dbi.read_cnf('/path/to/any/dsn_file')

Or use dbi.cache_cnf() in the same way.

Your credentials file must specify a database to connect to in the [mysql]
section. You can optionally assign or modify that value or use the
select_db() method on the connection, like this:

dsn['database'] = 'wmdb'     # the database we want to connect to

or

conn = dbi.connect(dsn)
conn.select_db('wmdb')

Use the DSN (credentials dictionary) to connect to the database. From here
on, mostly use the PyMySQL API.

conn = dbi.connect(dsn)
conn.select_db('wmdb')
curs = db.dict_cursor(conn)
curs.execute('select name,birthdate from person')
curs.execute('select name,birthdate from person where name like %s',
             ['%george%'])
curs.fetchall()
curs.fetchone()

Shortest Incantations:

    conn = dbi.connect()
    curs = dbi.dict_cursor(conn)

    conn = dbi.connect()
    curs = dbi.cursor(conn)

'''

import pymysql
import configparser
import os

# got this code from pymsql/optionfile.py

class Parser(configparser.RawConfigParser):

    def __remove_quotes(self, value):
        quotes = ["'", "\""]
        for quote in quotes:
            if len(value) >= 2 and value[0] == value[-1] == quote:
                return value[1:-1]
        return value

    def get(self, section, option):
        value = configparser.RawConfigParser.get(self, section, option)
        return self.__remove_quotes(value)

def read_cnf(cnf_file='~/.my.cnf'):
    '''Read a file formatted like ~/.my.cnf file; defaulting to that
    file. Return a dictionary with the necessary information to connect to
    a database. See the connect() function.'''
    abs_cnf_file = os.path.expanduser(cnf_file)
    if not os.path.exists(abs_cnf_file):
        raise FileNotFoundError(cnf_file)

    # this code is from pymysql/connections.py
    read_default_group = "client"
    cfg = Parser()
    cfg.read(abs_cnf_file)

    def _config(key):
        return cfg.get(read_default_group, key)

    user = _config("user")
    password = _config("password")
    host = _config("host")
    # on Tempest, we put the database in the mysql group
    database = cfg.get("mysql","database")
    return {'user': user,
            'password': password,
            'host': host,
            'database': database}

DSN_CACHE = None

def cache_cnf(cnf_file='~/.my.cnf'):
    '''Like read_cnf but reads the CNF file only once and caches the results'''
    global DSN_CACHE
    if DSN_CACHE is None:
        DSN_CACHE = read_cnf(cnf_file)
    return DSN_CACHE

def use(database):
    '''Like the 'use' statement, but modifies the cached cnf. Then connect()'''
    if DSN_CACHE is None:
        raise Exception('You have to invoke cache_cnf first')
    DSN_CACHE['database'] = database

def connect(dsn=cache_cnf('~/.my.cnf')):
    '''Returns a new database connection given the dsn (a dictionary). The
default is to use cache_cnf('~/.my.cnf')

    The database connection is not set to automatically commit.

    '''
    check_DSN(dsn)
    try:
        # have no idea why this unix_socket thing is necessary, but
        # only for deployed apps, not in development mode
        # see stackoverflow.com/questions/6885164/pymysql-cant-connect-to-mysql-on-localhost
        conn = pymysql.connect( use_unicode=True,
                                autocommit=False,
                                charset='utf8',
                                # commenting this out on minervadiabetes.net
                                # maybe file permissions?
                                # unix_socket='/var/lib/mysql/mysql.sock',
                                **dsn )
    except pymysql.Error as e:
        print("Couldn't connect to database. PyMySQL error {}: {}"
              .format(e.args[0], e.args[1]))
        raise
    return conn

def check_DSN(dsn):
    '''Raises a comprehensible error message if the DSN is missing
    some necessary info'''
    for key in ('host', 'user', 'password', 'database' ):
        if not key in dsn:
            raise KeyError('''DSN lacks necessary '{k}' key'''.format(k=key))
    return True

def select_db(conn,db):
    '''This function isn't necessary; just use the select_db() method
on the connection.'''
    conn.select_db(db)

def cursor(conn):
    '''Returns a cursor where rows are represented as tuples.'''
    return conn.cursor()

def dict_cursor(conn):
    '''Returns a cursor where rows are represented as dictionaries.'''
    return conn.cursor(pymysql.cursors.DictCursor)

def dictCursor(conn):
    '''Returns a cursor where rows are represented as dictionaries.'''
    return conn.cursor(pymysql.cursors.DictCursor)

if __name__ == '__main__':
    print('starting test code')
    import sys
    import os
    if len(sys.argv) < 2:
        print('''Usage: {cmd} cnf_file
test dbconn by giving the name of a cnf_file on the command line'''
              .format(cmd=sys.argv[0]))
        sys.exit(1)
    cnf_file = sys.argv[1]
    DSN = cache_cnf(cnf_file)
    print('Your DSN / CNF file should connect you as user {}@{} to database {}'
          .format(DSN['user'], DSN['host'], DSN['database']))
    conn = connect(DSN)
    print('successfully connected')

