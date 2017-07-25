# some utility functions
import pandas
import math
import numpy

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

def render(alist):
    for sublist in alist:
        sym = sublist[0]
        val = sublist[1]
        print sym,val
        if type(val) == int:
            sublist.append('<p>Integer {symbol}: {val}</p>'.format(symbol=sym,val=val))
        elif type(val) == numpy.float64:
            sublist.append('<p>Float {symbol}: {val}</p>'.format(symbol=sym,val=val))
        elif type(val) == type(True):
            sublist.append('<p>Boolean {symbol}: {val}</p>'.format(symbol=sym,val=val))
        elif type(val) == list:
            # assume a list of strings, explaining some calculation
            sublist.append('<p>{symbol}: {val}</p>'.format(symbol=sym,val=''.join(val)))
        elif type(val) == type(pandas.to_datetime('3/4/16')):
            sublist.append('<p>Datetime {symbol}: {val}</p>'.format(symbol=sym,val=val.strftime('%m/%d/%y %H:%M')))
        elif type(val) == type(pandas.Timedelta(hours=1)):
            sublist.append('<p>Timedelta {symbol}: {val}'.format(symbol=sym, val=val.__str__()))
        elif type(val) == type(pandas.DataFrame()):
            table = ['<table class="bordered">']
            table.append( '<tr>' )
            table.append( ''.join(['<th>{head}</th>'.format(head=c) for c in val.columns ]) )
            table.append( '</tr>\n' )
            for i in range(len(val)):
                table.append( '<tr>' )
                table.append( ''.join(['<td>{data}</td>'.format(data=nan2blank(val[c][i])) for c in val.columns ]) )
                table.append( '</tr>' )
            table.append('</table>')
            sublist.append('<h3>Dataframe {head}</h3>\n'.format(head=sym) + ''.join(table))
        else:
            raise ValueError('no render for {sym} with {val}'.format(sym=sym,val=val))
    return alist
            
            
