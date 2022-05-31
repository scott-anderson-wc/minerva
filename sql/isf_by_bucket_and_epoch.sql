-- We believe that time of day (time_bucket) is an important predictor of ISF
-- We also believe that age is a predictor, in the sense that it changes over time
-- We'll do a multiple regression to determine if these are supported.
-- For this data dump, we will just dump 1/0 whether the year is >= 2017
-- compare this with Mina's plots: '/isfCompareEarlyLate/'

select isf,time_bucket(rtime),if(year(rtime)>=2017,1,0) from isf_details;


