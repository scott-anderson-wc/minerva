# some utility functions
import math
import datetime
import flask
import cs304dbi as dbi
import json

DSN = None

def get_dsn(file='/home/hugh9/.my.cnf'):
    if DSN is None:
        DSN = dbi.read_cnf('/home/hugh9/.my.cnf')
    return DSN

def get_db_connection():
    g = flask.g
    conn = getattr(g, 'conn', None)
    if conn is None:
        conn = g.conn = dbi.connect(get_dsn())
    return conn

def get_dict_cursor():
    conn = get_db_connection()
    return dbi.dict_cursor(conn)
    
def dict2str(a_dict):
    '''returns a string for a dictionary-like object'''
    pairs = [ k + ': ' + v for k,v in a_dict ]
    return '{' + ','.join(pairs) + '}'

def floaty(str):
    if str=='':
        return 0.0
    else:
        return float(str)

def iso_to_readable(val_str):
    isoformat = '%Y-%m-%dT%H:%M:%S'
    readable = '%I:%M %p'
    return datetime.datetime.strptime(val_str,isoformat).strftime(readable)


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
    elif type(val) == type(True):
        sym_value_list.append('<p>Boolean {symbol}: {val}</p>'.format(symbol=sym,val=val))
    elif type(val) == list:
        if type(val[0]) == type(''):
            # assume a list of strings, explaining some calculation
            sym_value_list.append('<p>{symbol}: {val}</p>'.format(symbol=sym,val=''.join(val)))
        elif type(val[0]) == type({}):
            # assume a list of dictionaries, format as a table
            table = ['<table class="bordered">']
            cols = list(val[0].keys())
            table.append('<tr>')
            table.append(''.join(['<th>{head}</th>'.format(head=c)
                                  for c in cols]))
            table.append( '</tr>\n' )
            for row in val:
                table.append('<tr>')
                table.append(''.join(['<td>{data}</td>'.format(data=row[col])
                                      for col in cols]))
                table.append( '</tr>\n' )
            table.append('</table>')
            sym_value_list.append('<p>{symbol}: {val}</p>'.format(symbol=sym,
                                                                  val=''.join(table)))
    elif type(val) == type({}):
        # punt with JSON for now
        sym_value_list.append(json.dumps(val))
    else:
        raise ValueError('no render for {sym} with {val}'.format(sym=sym,val=val))
            
def render(alist):
    '''Takes an association list, like the 'steps' key in 'addstep', and 
appends a rendering (to HTML) to each sublist'''
    print(('rendering an alist of length %s' % len(alist)))
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
        raise ValueError('''You already have a step called {sym}'''.format(sym=sym))
    print(('adding step ',sym,' with value ',val))
    steps[sym] = val
    return val


