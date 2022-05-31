import math

''' 
================================================================
run the model on all the known data, computing the estimate of good_bg,
and compare with actual good_bg. Compute the signed difference. Accumulate
1. total positive
2. total negative (should be equal)
3. total squared values
'''

def eval_model(model, df):
    '''argument is an array of values, like result.params. df is a pandas dataframe'''
    # order is important. Must match the order in the model, which is the order in the CSV
    # omitting the intercept, since that's not multiplied by a row element
    (intercept, prev_bg, bg_slope, isf, di, di_slope) = model
    # accumulators
    total_pos = 0
    total_neg = 0
    total_sq = 0
    num_vals = 0
    
    for index, row in df.iterrows():
        est = (intercept
               + prev_bg * row['prev_bg']
               + bg_slope * row['bg_slope']
               + isf * row['isf']
               + di * row['di']
               + di_slope * row['di_slope'])
        # est = 100
        num_vals += 1
        good_bg = row['good_bg']
        diff = est - good_bg
        if est > good_bg:
            total_pos += diff
        else:
            total_neg += diff
        total_sq += diff*diff
    # all done
    return total_pos/num_vals, total_neg/num_vals, total_sq/num_vals, math.sqrt(total_sq/num_vals), num_vals

def predictive_curve(model, df, row, basal_insulin, stride, duration_minutes=120):
    '''Returns N estimates of BG for `duration_minutes` starting at `row`,
one every 5 minutes.  The `stride` is the steps of the predictive
model, e.g. 5, 10, 15, 20, 30 minutes. Value is a list of tuples,
(rtime, bg)

The iterated predictive curve is based on the predicted values of di
and isf as well as bg. isf can just be computed from time of day, but
di has a whole curve behind it, based on basal insulin, so we need
that, too.

    '''
    
    
    

