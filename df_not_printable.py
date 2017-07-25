from flask import (Flask, render_template, make_response, request, redirect, url_for,
                   session, flash, send_from_directory)

import pandas
import numpy

application = Flask(__name__)

@application.route('/')
def index():
    df = pandas.DataFrame(numpy.random.randn(6,4), index=list('abcdef'),columns=list('ABCD'))
    print('df is ',df)
    return '<!doctype html><html><body>df is '+str(df)+'</body></html>'


if __name__ == '__main__':
    port = 5000
    application.run('0.0.0.0',port=port)
