'''Script to run at regular intervals to (typically every 5 minutes) to get the latest CGM from Dexcom. 

This is based on an original by Stan Kanner and Laura Scanlon written in Perl.

Data from Dexcom looks like this:

[{"WT":"Date(1659091309000)","ST":"Date(1659091309000)","DT":"Date(1659091309000-0400)","Value":49,"Trend":"FortyFiveDown"}]

A nice JSON format. Not sure why there are three date-fields with the
same value in each. The date field seems suitable to send to "new
Date(unix_timestamp)":

new Date(1659091309000)
Date Fri Jul 29 2022 06:41:49 GMT-0400 (Eastern Daylight Time)

Note that the minus sign in the last doesn't have the desired
effect. It seems to be there to indicate the time zone, but all it
really does is subtract 0.4 seconds. Dumb.

If Dexcom doesn't have any new data, it gives the newest it has,
timestamped. So, if you see the same newest timestamp more than once,
it means there's NoData. We detect that and store a NULL.

After a NoData event, Dexcom can catch you up. I don't think there's a
specific "catch up" situation, so I've decided to try to detect that
situation and fill it in. Many outages are short, so we can avoid a
second query by always asking for N data points, say 12 (one hour). If
the outage is longer than that, and there is new data, we can make a
second request.

So, the logic is

1. Get T, the newest timestamp with non-NULL data from realtime_cgm2
2. Compute N, the number of missing data. 
3. Request N data from Dexcom
4. if the newest timestamp from Dexcom matches T, 
    a. record NoData, else
    b. replace the NULLs with real data

I'll write T, N, and the result of the IF statement in the LOG

Scott D. Anderson
August 5, 2022

'''

import sys
import os
from datetime import datetime, timedelta
import date_ui
import requests
import json
import logging
import random                   # for error_id numbers
import html2text                # for readable messages from the Dexcom server
import cs304dbi as dbi

# Configuration Constants

LOG_DIR = '/home/hugh9/dexcom_logs/'
LOGIN_URL = 'https://share1.dexcom.com/ShareWebServices/Services/General/LoginPublisherAccountByName'
USER_AGENT_HEADER = 'Dexcom%20Share/3.0.2.11 CFNetwork/672.0.2 Darwin/14.0.0';
CGM_URL = 'https://share1.dexcom.com/ShareWebServices/Services/Publisher/ReadPublisherLatestGlucoseValues'
CRED_FILE = '/home/hugh9/dexcom-credentials.json'
# added this on 9/10/2022
HUGH_USER_ID = 7          # the user_id value stored in realtime_cgm2
HUGH_USER = 'Hugh'        # the username value stored in realtime_cgm2
TREND_VALUES = {'None': 0,
                'DoubleUp': 1,
                'SingleUp': 2,
                'FortyFiveUp': 3,
                'Flat': 4,
                'FortyFiveDown': 5,
                'SingleDown': 6,
                'DoubleDown': 7,
                'NotComputable': 8,
                'RateOutOfRange': 9
               }

def debugging():
    logging.basicConfig(level=logging.DEBUG)

# ?sessionId=' . $trimmedSessionId .'&minutes=1440&maxCount=1';

def get_latest_stored_data(conn):
    '''Looks up the latest data that we stored from previous inquiries.
Returns rtime and dexcom_time from last non-NULL value. We can infer
the number of values we need from Dexcom from those.

    '''
    curs = dbi.cursor(conn)
    curs.execute('''SELECT rtime, dexcom_time
                    FROM realtime_cgm2
                    WHERE user_id = %s and
                          rtime = (SELECT max(rtime) FROM realtime_cgm2
                                   WHERE user_id = %s and mgdl is not NULL)''',
                 [HUGH_USER_ID, HUGH_USER_ID])
    row = curs.fetchone()
    return row

def read_credentials(credfile=CRED_FILE):
    '''The Dexcom authentication credentials are stored in a file outside
of our Github repo, for security reasons. This file reads those. It's
a Python dictionary, stored in JSON format, with the following keys:
accountName, applicationId, password.'''
    with open(credfile, 'r') as fin:
        cred_dic = json.load(fin)
    required_keys = ['accountName', 'applicationId', 'password']
    for key in required_keys:
        if key not in cred_dic:
            raise Exception('missing key '+key)
    return cred_dic

def trim_quotes(x):
    '''if the string has quotation marks around it, strips the quotation marks'''
    if x[0] == '"' and x[-1] == '"':
        return x[1:-1]
    else:
        return x

session_cookies = None

def dexcom_login(creds):
    '''Returns sessionId which we use in requesting the CGM value'''
    global session_cookies
    resp = requests.post(LOGIN_URL,
                         data = json.dumps(creds),
                         headers = {'User-Agent': USER_AGENT_HEADER,
                                    'Content-Type': 'application/json'})
    if 'session' in dict(resp.cookies):
        logging.info('cookies were set!')
        session_cookies = resp.cookies
    if resp.ok:
        return trim_quotes(resp.text)
    # 6/22/2023 Sometimes the service isn't available. That's not a
    # bug, so let's try to detect it and just log the fact
    if resp.status_code == 503 and resp.reason == 'Service Unavailable':
        logging.info('Service Unavailable')
        sys.exit()
    # similarly 504
    if resp.status_code == 504 and resp.reason == 'Gateway Time-out':
        logging.info('Gateway Time-out')
        sys.exit()
    raise Exception('bad login request or response',
                    [resp.status_code, resp.reason, html2text.html2text(resp.text)] )

def extract_unix_epoch(dexcom_date_string):
    '''Given a string like Date(1659091309000) or Date(1659091309000-0400) returns the string of digits'''
    pref = 'Date('
    suff = ')'
    date_string = dexcom_date_string
    if (date_string[0:len(pref)] == pref and
        date_string[-1] == suff):
        epoch_tz = date_string[len(pref):-1]
        tz_pos = epoch_tz.find('-')
        if tz_pos == -1 and epoch_tz.isdigit():
            return epoch_tz
        elif tz_pos != -1:
            # extract the part before the time zone
            epoch = epoch_tz[0:tz_pos]
            return epoch
        else:
            log_write("ERROR: no match for date format with unix timestamp: "+date_string)
            return 0            # can be converted to a (bogus) datetime

def convert_to_datetime(dexcom_date_string):
    epoch = extract_unix_epoch(dexcom_date_string)
    if epoch.isdigit():
        return datetime.fromtimestamp(int(epoch)//1000)
    else:
        return datetime.fromtimestamp(0)

def dexcom_cgm_values_raw(session_id, max_count=1):
    '''Makes request to Dexcom and returns text of the response. Should
look like JSON, list of dictionaries of length max_count.'''
    resp = requests.get(CGM_URL,
                        {'sessionId': session_id,
                         # 24 hours of data. Might be excessive
                         'minutes': 1440, 
                         # MaxCount cannot be null
                         'MaxCount': max_count
                         })
    if resp.ok:
        return resp.text
    # 6/22/2023 Sometimes the service isn't available. That's not a
    # bug, so let's try to detect it and just log the fact
    if resp.status_code == 503 and resp.reason == 'Service Unavailable':
        logging.info('Service Unavailable')
        sys.exit()
    # similarly 504
    if resp.status_code == 504 and resp.reason == 'Gateway Time-out':
        logging.info('Gateway Time-out')
        sys.exit()
    # 7/11/2023 Sometimes we get an Internal Server Error
    if resp.status_code == 500:
        logging.info('Internal Server Error')
        sys.exit()
    # something else went wrong. Give it an id
    error_id = random.randint(1, 1000)
    logging.error(f'{error_id} bad CGM request or response. status_code: {resp.status_code} ')
    logging.error(str(error_id)+html2text.html2text(resp.text).replace('\n',' '))
    raise Exception(f'bad cgm request or response, search logs for {error_id}',
                    [resp.status_code, resp.reason, html2text.html2text(resp.text)] )

def parse_cgm_values(raw_data):
    json_data = json.loads(raw_data)
    if type(json_data) is not type([]):
        logging.error('ERROR: response is not a list of dictionaries')
    for d in json_data:
        wt = d['WT'] = convert_to_datetime(d['WT'])
        st = d['ST'] = convert_to_datetime(d['ST'])
        dt = d['DT'] = convert_to_datetime(d['DT'])
        if not dt == st == dt:
            logging.error('time values disagree: {} {} {}'.format(wt, st, dt))
    return json_data

def dexcom_cgm_values(session_id, max_count):
    '''reads Dexcom values and converts to JSON and converts date
values. Complains if there are errors. Returns JSON, list of dictionaries.'''
    raw_data = dexcom_cgm_values_raw(session_id, max_count)
    logging.info('raw data: '+raw_data)
    return parse_cgm_values(raw_data)

def log_file_name():
    today = datetime.today()
    day = today.day
    return os.path.join(LOG_DIR, 'day'+str(day))

def write_cgm(conn, text_data, wt_time, rtime_now):
    '''write a single CGM value (and trend) into the realtime_cgm2 table,
might be an old value.'''
    curs = dbi.cursor(conn)
    mgdl = text_data.get('Value')
    trend_code = text_data.get('Trend') # an ENUM 
    if mgdl is None:
        logging.error('mgdl is missing')
    if trend_code is None:
        logging.error('trend is missing')
    # try to avoid storage errors/complaints. Update this if there are new codes
    trend_num = TREND_VALUES.get(trend_code)
    if trend_num is None:
        logging.error('trend is invalid: {}'.format(trend_code))
    logging.debug('rtime {} WT {} value {}'.format(rtime_now,wt_time,mgdl))
    nrows = curs.execute('''INSERT INTO realtime_cgm2(user_id, user, rtime, dexcom_time, mgdl, trend, trend_code) 
                            VALUES(%s,%s,%s,%s,%s,%s,%s)
                            ON DUPLICATE KEY UPDATE
                               dexcom_time = values(dexcom_time),
                               mgdl = values(mgdl),
                               trend = values(trend),
                               trend_code = values(trend_code)''',
                         [HUGH_USER_ID, HUGH_USER, rtime_now, wt_time, mgdl, trend_num, trend_code ])
    conn.commit()
    return nrows
    
def write_no_data(conn, rtime_now):
    '''write a NoData event into the realtime_cgm2 table.'''
    curs = dbi.cursor(conn)
    curs.execute('''INSERT INTO realtime_cgm2(user_id, user, rtime, mgdl, trend, trend_code) 
                    VALUES(%s,%s,%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE mgdl = NULL, trend = NULL, trend_code = NULL''',
                 [HUGH_USER_ID, HUGH_USER, rtime_now, None, None, None])
    conn.commit()
    
  

def replace_missing_data(conn, cgm_values):
    # Let's try to update with the new data.
    # I'm going to convert each dexcom timestamp to an rtime,
    # rounding UP and use that for replacing missing values.
    for d in cgm_values:
        wt = d['WT']
        rt = date_ui.to_rtime(wt) + timedelta(minutes=5)
        logging.debug('old data RT: {} WT: {}'.format(str(wt),str(rt)))
        nrows = write_cgm(conn, d, wt, rt)
        if nrows != 2:
            logging.error("update with new data didn't yield 2 modified rows: nrows = {} wt = {} rtime = {}".format(nrows, wt, rt))

def get_cgm():
    '''This puts all the pieces together. There are basically 4 scenarios: 
1. up to date, get 1 record and store it,
2. up to date, but the record is a repeat, so record NoData
3. need to catch up, get N records and store them.
4. need to catch up, but still getting old data, so record NoData'''
    now = datetime.today()
    rtime_now = date_ui.to_rtime(now)
    rtime_prev = rtime_now - timedelta(minutes=5)
    conn = dbi.connect()
    stored_rtime, stored_dexcom_time = get_latest_stored_data(conn)
    logging.debug('stored times {} and {}'.format(stored_rtime, stored_dexcom_time))
    creds = read_credentials()
    session_id = dexcom_login(creds)
    cgm_values = None           # will be our return value
    if stored_rtime == rtime_prev:
        logging.info('Normal case: all up to date, so just get one data value')
        cgm_values = dexcom_cgm_values(session_id, 1)
        cgm = cgm_values[0]
        logging.debug('cgm values: '+str(cgm))
        wt_time = cgm['WT']
        # check for NoData
        if wt_time == stored_dexcom_time:
            logging.info('CASE2 no data')
            write_no_data(conn, rtime_now)
        else:
            logging.info('CASE1 normal update, one row')
            write_cgm(conn, cgm, wt_time, rtime_now)
    else:
        logging.info('latest value is > 5 minutes old; we need to catch up')
        # NOT up to date, so get several data values, hoping to fill in missing values
        time_diff = rtime_now - stored_rtime
        count = time_diff.seconds // (60*5)
        # add one, just to be sure
        cgm_values = dexcom_cgm_values(session_id, count+1)
        logging.debug('requested {} values, got {} values'.format(count, len(cgm_values)))
        # so many things could go wrong. Are they all different
        # timestamp values? We might *still* be in a NoData situation.
        cgm = cgm_values[0]
        first_wt = cgm['WT']
        logging.debug('first returned WT is {} versus stored {}'.format(first_wt, stored_dexcom_time))
        if first_wt == stored_dexcom_time:
            logging.info('CASE4 still in no data state; write null')
            write_no_data(conn, rtime_now)
        else:
            logging.info('CASE3 got new data, try to update')
            replace_missing_data(conn, cgm_values)
    return cgm_values

def get_data(count):
    creds = read_credentials()
    session_id = dexcom_login(creds)
    cgm_values = dexcom_cgm_values(session_id, count)
    return cgm_values


def test1():
    '''returns 10 Dexcom values as JSON'''
    creds = read_credentials()
    session_id = dexcom_login(creds)
    data = dexcom_cgm_values(session_id, 10)
    for d in data:
        print(d)
    return data

def test2():
    '''process a file of dexcom data, finding whether timestamps ever
differ and how the timestamps relate to rtimes. This shows that the
timestamp from Dexcom is always before the rtime (not surprising) but
sometimes quite a bit.'''
    with open('/home/hugh9/WT2.log', 'r') as fin:
        for line in fin:
            l = line.split(' ')
            t = l[0]
            script_time = datetime.strptime('%H:%M')
            d = json.loads(l[1])[0]
            wt = d['WT'] = convert_to_datetime(d['WT'])
            st = d['ST'] = convert_to_datetime(d['ST'])
            dt = d['DT'] = convert_to_datetime(d['DT'])
            if not dt == st == dt:
                print('ERROR: time values disagree: {} {} {}'.format(wt, st, dt))

            if (wt.minute % 5) != 0:
                print(t+' '+wt.strftime('%H:%M:%S'))

def test3():
    '''the first few steps of the algorithm'''
    now = datetime.today()
    rtime_now = date_ui.to_rtime(now)
    rtime_prev = rtime_now - timedelta(minutes=5)
    conn = dbi.connect()
    stored_rtime, stored_dexcom_time = get_latest_stored_data(conn)
    creds = read_credentials()
    session_id = dexcom_login(creds)
    print('session id', session_id)
    if stored_rtime == rtime_prev:
        # Normal case: all up to date, so just get one data value
        logging.info('normal case')
        cgm_values = dexcom_cgm_values(session_id, 1)
        cgm = cgm_values[0]
        logging.debug('cgm values: '+cgm)
        wt_time = cgm['WT']
        # check for NoData
        if wt_time == stored_dexcom_time:
            logging.info('no data')
            write_no_data(conn, rtime_now)
        else:
            logging.info('normal data')
            write_cgm(conn, cgm, wt_time, rtime_now)
    else:
        logging.info('not up to date; try to get old data')


if __name__ == '__main__':
    # when run as a script, log to a logfile 
    today = datetime.today()
    logfile = os.path.join(LOG_DIR, 'day'+str(today.day))
    logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s',
                        datefmt='%H:%M',
                        filename=logfile,
                        level=logging.DEBUG)
    get_cgm()
