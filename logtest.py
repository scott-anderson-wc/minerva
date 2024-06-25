import os
import logging
from datetime import datetime

'''Logging doesn't want to log to different files, at least with
BasicConfig. This uses two globals to log to a different file at
different times.  

'''

logstream = None
loghandler = None

LOG_DIR = ''

def start(source, count):
    # The default is to run as a cron job
    # when run as a script, log to a logfile 
    global logstream, loghandler
    today = datetime.today()
    logfile = os.path.join(LOG_DIR, source+str(today.day))
    print('logfile',logfile)
    now = datetime.now()
    if now.hour == 0 and now.minute==0:
        try:
            os.unlink(logfile)
        except FileNotFoundError:
            pass
    # The logging software doesn't allow more than one basicConfig, so
    # logging to different files is difficult. 
    logstream = open(logfile, 'a')
    h = logging.StreamHandler(logstream)
    logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s',
                        datefmt='%H:%M',
                        level=logging.DEBUG)
    logger = logging.getLogger()
    if loghandler is not None:
        logger.removeHandler(loghandler)
    loghandler = h
    logger.addHandler(loghandler)
    if now.hour == 0 and now.minute==0:
        logging.info('================ first run of the day!!'+str(now))
    logging.info('SCOTT running at {} logging {} and {}'.format(datetime.now(), logfile, count))

if __name__ == '__main__': 
    start('foo', 1)
    logstream.close()
    start('bar', 2)
    logstream.close()
    
