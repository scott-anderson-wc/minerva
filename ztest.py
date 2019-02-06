import math
import MySQLdb
from dbi import get_dsn, get_conn # connect to the database

def ztest(condition):
    conn = get_conn()
    curs = conn.cursor()
    curs.execute('''
select {cond} as grp, avg(isf) as mean, stddev(isf) as sd,count(isf) as n
from isf_details
where year(rtime) >= 2017
group by {cond}
    '''.format(cond=condition))
    (grp1, mean1, sd1, n1) = curs.fetchone()
    (grp2, mean2, sd2, n2) = curs.fetchone()
    print (grp1, mean1, sd1, n1)
    print (grp2, mean2, sd2, n2)
    sp = math.sqrt( ( (n1-1)*sd1*sd1 + (n2-1)*sd2*sd2) / (n1+n2-2) )
    print 'pooled sp', sp
    diff = mean1 - mean2
    print 'diff ',diff
    t = diff / (sp * math.sqrt( (1/float(n1)) + (1/float(n2)) ) )
    return (mean1, mean2, diff, sp, t)

if __name__ == '__main__':
    # print ztest('year(rtime) < 2017')
    print ztest('bg0 > 200')
                 
    
