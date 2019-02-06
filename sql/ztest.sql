select month(rtime)<6 as grp, avg(isf) as mean, stddev(isf) as sd,count(isf) as n
from isf_details
where year(rtime)=2018
group by month(rtime)<6;
