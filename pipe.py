'''Function to create a pipeline of functions that each acts like an
element of a Unix pipeline: reading from its arg (an iterator) and
generating elements.'''

from __future__ import print_function
import functools
from itertools import islice, count

# from //mathieularose.com/function-composition-in-python/

# except that I want them to go from first to last instead of outer to
# inner For consistency, all take one arg, so the innermost one can just
# ignore that arg and return an iterator.

def pipe(*funcs):
    def compose2(f, g):
        return lambda x: f(g(x))
    funcs = list(funcs)
    funcs.reverse()
    return functools.reduce(compose2, funcs, lambda x: x)

def testpipe1():
    def f(x):
        return [1,2,3]
    def f1(seq):
        for s in seq:
            yield s*s
    def f2(seq):
        for s in seq:
            yield s+1
    g1 = pipe( f, f1, f2 )
    print(list(g1(None)))
    g2 = pipe( f, f2, f1 )
    print(list(g2(None)))

def testpipe2():
    def fromone(x):
        return count(1)
    def square(seq):
        for s in seq:
            yield s*s
    def incr(seq):
        for s in seq:
            yield s+1
    g = pipe( fromone,
              lambda seq: tee(seq, prefix='x '),
              square,
              lambda seq: tee(seq, prefix='x^2 '),
              incr,
              more )
    g(None)


def printall(source):
    for s in source:
        print(s)
        yield s

def exhaust(source,progress=None):
    n = 0
    try:
        while True:
            n += 1
            if progress is not None and n % progress == 0:
                print('progress: {n}'.format(n=n))
            source.next()
    except StopIteration:
        return 'Iteration is exhausted'
        
def more(source,page=20,printer=print):
    i = 1
    print('print function is ',printer)
    try:
        while True:
            while i<page:
                i += 1
                printer(source.next())
            ans = raw_input('more? y/n ')
            if ans != 'y':
                break
            i = 1
    except StopIteration:
        return 'Iteration is exhausted'
    
def cat(source):
    for s in source:
        yield s

def tee(source,prefix='',stringify=str,printer=print):
    for s in source:
        printer(prefix+stringify(s))
        yield s

def mapiter(source,func):
    for s in source:
        yield func(s)

def average(seq):
    # print('in average, seq is ',seq)
    return sum(seq)/len(seq)

def shift(elts,new):
    for i in xrange(len(elts)-1):
        elts[i] = elts[i+1]
    elts[len(elts)-1] = new

def shiftdown(elts,new):
    for i in xrange(len(elts)-1):
        elts[i+1] = elts[i]
    elts[0] = new

def test_shift():
    x = [1,2,3,4,5]
    print(x)
    shift(x,6)
    print(x)
    shift(x,7)
    print(x)
    shift(x,8)
    print(x)
    shift(x,9)
    print(x)
    shift(x,10)
    print(x)

def do_window(rows, size=5):
    win = []
    while len(win) < size:
        win.append(rows.next())
    while True:
        avg = average(win)
        shift(win,rows.next())
        yield avg

# ================================================================


def test1():
    exhaust(printall(islice(count(1), 20)))

def test2():
    more(islice(count(1), 200))

def test3():
    more(mapiter(count(1), lambda x: x*x))
    
def test4():
    more(mapiter(count(1), lambda x: x*x),
         printer=lambda x: print('x is ',x))
    
def test5():
    more(mapiter(tee(count(1),prefix='x:'),
                 lambda x: x*x),
         printer=lambda x: print('x^2 is ',x))
    
def test6():
    more(do_window(count(1)))
