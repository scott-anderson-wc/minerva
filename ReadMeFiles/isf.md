ISF information:

Files:
isf2.py
md.py
md_deploy.py

Templates:
isf2.html
isfcompare.html
isfplots.html
isf-display.html

Routes in md.py (not deployed) 

'/browseisf/'
- A route to see information for the 2.5 hours span when a correction bolus is given
- Uses method get_isf(date) to get isf data given a date.

'/isfCompareEarlyLate/'
- Route to compare 2014-2016 data vs 2017-2018 data separated by time bucket for easy comparison
- Uses method get_isf_for_years to get isf for comparisons

'/isfCompareBG/'
- Route to compare isf data greater than and less than a given BG value (given 200)
- Uses method get_isf_for_bg to get isf data for comparisons


Routes in md_deploy.py

'/getRecentISF/<int:time_bucket>/<int:min_weeks>/<int:min_data>/'
- Gets the most recent min_data isf data for a given time bucket within min_weeks (if there is enough data within the number of weeks)
- Uses method getRecentISF to get isf data 

'/isfplots'
- A route to see all isf data in a box and whisker plot sorted in 2-hour time buckets
- Uses method get_all_isf_plus_buckets to get all isf data an d isf data for each 2-hour time bucket

Key Methods in isf2.py

compute_isf
- computes isf values
- Calculated isf values are "good" if following criteria are met
  1. No corrective insulin within 1hr40 min before current corrective insulin
  2. Total bolus amount it too small
  3. No bolus given in middle time frame
  4. BG or CGM levels given for start and end time or within 10min of those times
- Updates isf_details table with computed isf values
- Update insulin_carb_smoothed with isf value or reason why trouble computing isf value

get_all_isf_plus_buckets
- Gets all isf values from isf_details and returns data along with isf values in 2-hour time buckets

get_isf_for_years
- Gets all isf values from isf_details within a given time span (in years) and returns data along with isf values in 2-hour time buckets

get_isf_for_bg
- Gets all isf values from isf_details greater than and less than a given bg, also returns time-bucketed data

getRecentISF
- Recrusively finds the smallest number of weeks (if not enough data within given num
_weeks time span) of isf data given a time bucket to return at least min_data data points
       - If min_data or more data points are found after searching min_weeks ==> Return
       - if not, double min_weeks to find the upper bound number of weeks needed to find min_data points
       - Then peform a binary search to find the correct number of weeks needed


