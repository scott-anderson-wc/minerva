# some utility functions

def dict2str(a_dict):
    '''returns a string for a dictionary-like object'''
    pairs = [ k + ': ' + v for k,v in a_dict ]
    return '{' + ','.join(pairs) + '}'
