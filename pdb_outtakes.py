def excess_basal_insulin_post_meal_v1(df,prior_basal):
    '''returns the sum of excess basal insulin multiplied by time-interval
for the post-meal period. The basal insulin is a rate in units/hour,
right?  This calculation goes for six hours after the meal begins'''
    calcs = []                  # for documentation
    first_time = df.date_time[0]
    prior_time = df.date_time[0]
    last_time = df.date_time[-1]
    six_hours = pandas.Timedelta(hours=6)
    if last_time - prior_time < six_hours:
        raise ValueError('Did not have 6 hours of data')
    running_total = 0
    for row in df.itertuples():
        if row.date_time - first_time > six_hours:
            break
        if (not math.isnan(row.basal_amt) and
            row.basal_amt > prior_basal):
            td = (row.date_time - prior_time) # a pandas Timedelta object
            excess = row.basal_amt - prior_basal
            hrs = td.total_seconds()/(60*60)
            amt = excess * hrs
            calc = ("({curr} - {base})*{time} = {excess}*{hrs} = {amt}"
                    .format(curr=row.basal_amt,
                            base=prior_basal,
                            time=td,
                            excess=excess,
                            hrs=hrs,
                            amt=amt
                    ))
            calcs.append(calc)
            running_total += amt
            prior_time = row.date_time # new prior time
    print 'total excess: ',running_total
    return calcs, running_total

