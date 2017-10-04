# some utility functions
import pandas
import math
import numpy
import flask
import dbconn2

DSN = None

def get_dsn(file='/home/hugh9/.my.cnf'):
    if DSN is None:
        DSN = dbconn2.read_cnf('/home/hugh9/.my.cnf')
    return DSN

def get_db_connection():
    g = flask.g
    conn = getattr(g, 'conn', None)
    if conn is None:
        conn = g.conn = dbconn2.connect(get_dsn())
    return conn

def get_dict_cursor():
    conn = get_db_connection()
    return conn.cursor(MySQLdb.cursors.DictCursor)
    
def dict2str(a_dict):
    '''returns a string for a dictionary-like object'''
    pairs = [ k + ': ' + v for k,v in a_dict ]
    return '{' + ','.join(pairs) + '}'

def floaty(str):
    if str=='':
        return 0.0
    else:
        return float(str)

def nan2blank(x):
    if type(x)==numpy.float64 and math.isnan(x):
        return '&nbsp;'
    else:
        return x

def render1(sym_value_list):
    '''Appends a rendering (to HTML) of a list of a symbol and its value'''
    if type(sym_value_list) != type([]):
        raise TypeError('sym_value_list is not a list: ',sym_value_list)
    sym = sym_value_list[0]
    val = sym_value_list[1]
    # print('current elt is {s}: {v}'.format(s=sym,v=val))
    if type(val) == int:
        sym_value_list.append('<p>Integer {symbol}: {val}</p>'.format(symbol=sym,val=val))
    elif type(val) == float:
        sym_value_list.append('<p>Float {symbol}: {val}</p>'.format(symbol=sym,val=val))
    elif val is None:
        sym_value_list.append('<p>{symbol}: None</p>'.format(symbol=sym))
    elif type(val) == numpy.float64:
        sym_value_list.append('<p>Float {symbol}: {val}</p>'.format(symbol=sym,val=val))
    elif type(val) == type(True):
        sym_value_list.append('<p>Boolean {symbol}: {val}</p>'.format(symbol=sym,val=val))
    elif type(val) == list:
        # assume a list of strings, explaining some calculation
        sym_value_list.append('<p>{symbol}: {val}</p>'.format(symbol=sym,val=''.join(val)))
    elif type(val) == type(pandas.to_datetime('3/4/16')):
        sym_value_list.append(('<p>Datetime {symbol}: {val}</p>'
                               .format(symbol=sym,val=val.strftime('%m/%d/%y %H:%M'))))
    elif type(val) == type(pandas.Timedelta(hours=1)):
        sym_value_list.append('<p>Timedelta {symbol}: {val}'.format(symbol=sym, val=val.__str__()))
    elif type(val) == type(pandas.DataFrame()):
        table = ['<table class="bordered">']
        table.append( '<tr>' )
        table.append( ''.join(['<th>{head}</th>'.format(head=c) for c in val.columns ]) )
        table.append( '</tr>\n' )
        for i in range(len(val)):
            table.append( '<tr>' )
            table.append( ''.join(['<td>{data}</td>'.format(data=nan2blank(val[c][i]))
                                   for c in val.columns ]) )
            table.append( '</tr>' )
            table.append('</table>')
            sym_value_list.append('<h3>Dataframe {head}</h3>\n'.format(head=sym) + ''.join(table))
    else:
        raise ValueError('no render for {sym} with {val}'.format(sym=sym,val=val))
            
def render(alist):
    '''Takes an association list, like the 'steps' key in 'addstep', and 
appends a rendering (to HTML) to each sublist'''
    print('rendering an alist of length %s' % len(alist))
    for sublist in alist:
        render1(sublist)
            
def addstep(steps, sym, val):
    '''add a new step (sym, val) pair, to a dictionary of steps. Special key 'steps' gives them in order'''
    if sym == 'steps':
        raise ValueError('''Cannot name a step 'steps': %{sym}'''.format(sym=sym))
    if 'steps' not in steps:
        steps['steps'] = []
    sublist = [sym,val]
    render1(sublist)
    steps['steps'].append(sublist)
    if sym in steps:
        raise ValueError('''You already have a step called %{sym}'''.format(sym=sym))
    print('adding step ',sym,' with value ',val)
    steps[sym] = val
    return val


