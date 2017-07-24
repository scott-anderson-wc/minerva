import sys
import os

def body(msg):
    html = '''<!doctype html>
<html lang='en'>
<head>
    <meta charset='utf-8'>
    <title>WSGI Test</title>
</head>
<body>
    <h1>WSGI Test</h1>
    <p>This server is running WSGI using Python version {pyversion}</p>
    <p>Python Path is {pypath}</p>
    <p>It is running as {uid}</p>
    <p>{msg}</p>
</body>
</html>
'''
    return html.format(pyversion=sys.version,
                       pypath=sys.path,
                       uid=os.getuid(),
                       msg=msg
    )

import md

def application(environ, start_response):
    status = '200 OK'
    response_header = [('Content-type','text/html')]
    start_response(status,response_header)
    # debugging output goes to wsgi.errors; which should be the Apache log
    print >> environ['wsgi.errors'],'Scott: a debug message from my application'
    try:
        return md.app(environ, start_response)
        print >> environ['wsgi.errors'],'Scott: md success'
    except Exception as err:
        print >> environ['wsgi.errors'], 'Exception during execution:'
        print >> environ['wsgi.errors'], err
        start_response('500 Internal Server Error',response_header)
        return [body('exception during execution; see logs')]

