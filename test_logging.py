from datetime import datetime
import logging
import os

LOG_DIR = '/home/hugh9/test_logs/'

def debugging():
    logging.basicConfig(level=logging.DEBUG)

def do_stuff():
    logging.info('this is info')
    logging.debug('debug: '+LOG_DIR)
    logging.error('Yikes!')

if __name__ == '__main__':
    # when run as a script, log to a logfile 
    today = datetime.today()
    logfile = os.path.join(LOG_DIR, 'day'+str(today.day))
    logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s',
                        datefmt='%H:%M',
                        filename=logfile,
                        level=logging.DEBUG)
    do_stuff()
