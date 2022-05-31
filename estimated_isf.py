'''Much of isf2.py is calculating ISF values, but it also includes
code it compute an estimated ISF value based on recent historical date
(this quarter, the previous quarter ...) and the current time bucket
(0-11) or, sometimes, neighboring time buckets. 

The calculation is complicated and the result holds for an entire
quarter, so it's ripe for pre-computing and storing.

I've written sql/create_estimated_isf.sql to define an estimated_isf
table, with the key being all the data we use to request an estimated
isf value (see the est_isf_cache dictionary in isf2), namely

(bucket, year, quarter)

the data is

isf

there's also some info about how the estimate was derived. These are
values stored in the est_isf_cache and written by est_isf_table()

option (how the estimate was determined)
len (the number of values we found)

There are a *lot* of failures in recent years. Need to resolve that
before we can start using the estimated ISFs in the predictive model.

'''

