import dbconn2

DSN = None
Conn = None

def get_dsn():
    global DSN
    if DSN is None:
        DSN = dbconn2.read_cnf()
    return DSN

def get_conn(dsn=get_dsn()):
    global Conn
    if Conn is None:
        Conn = dbconn2.connect(dsn)
    return Conn
