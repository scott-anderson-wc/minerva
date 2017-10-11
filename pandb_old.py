'''The following definition was used on 10/4, but happens to exclude
changes to the basal that occurred during the mealtime (+/- 30 minutes
of carbs entry) but were not the max. Janice said that she'd like
those earlier basals computed, too.

'''

def basal_insulin_delta(df_rel, df_meal):

'''finds a basal_insulin 2 hours prior to meal. Returns 3 values:


On 8/4, Janice said look 2 hours before the meal; whatever the basal
insulin was then, use that as the pre-meal basal. So for the April 3rd
2016 example day, use 0.2 for the evening meal.
    '''
    global prior_recs, basal_amts
    thirty_mins = datetime.timedelta(hours = 0.5)
    win_start = df_meal.date_time[0] - thirty_mins 
    win_end = df_meal.date_time[len(df_meal)-1] + thirty_mins
    # find earlier basals
    two_hours = datetime.timedelta(hours=2)
    before_meal = df_meal.date_time[0] - two_hours
    # these are all the non-zero basals at least two hours before the meal
    df_prior_basals = select(df_rel,
                             lambda row:
                               (not pandas.isnull(row.basal_amt) and
                                not row.basal_amt == 0.0 and
                                row.date_time < before_meal))
    print 'df_prior_basals'
    print df_prior_basals
    if len(df_prior_basals) == 0:
        raise ValueError('figure out how to handle missing data')
    # This is the last value, so the most recent value
    prior = df_prior_basals.basal_amt[len(df_prior_basals)-1]
    print('prior: ',prior)
    # meal basals: all basal values within +/- 30 minutes of the meal
    df_meal_basals = select(df_rel,
                           lambda row:
                               (not pandas.isnull(row.basal_amt) and
                                row.basal_amt > prior and
                                row.date_time >= win_start and
                                row.date_time <= win_end))
    print 'df_meal_basals'
    print df_meal_basals
    if len(df_meal_basals) == 0:
        raise ValueError('figure out how to handle missing data')
    meal_basals = df_meal_basals.basal_amt
    meal_basals_max = meal_basals.max()
    meal_basals_min = meal_basals.min()
    if meal_basals_max > meal_basals_min:
        print('ignoring some mealtime basal settings')
    # Find the first record that has the change to meal_basal_max
    df_meal_basals_max = None
    for row in df_meal_basals.itertuples():
        if row.basal_amt == meal_basals_max:
            print('row: ',row)
            df_meal_basals_max = pandas.DataFrame([row._asdict()], columns = df_meal_basals.columns)
            break
    print('df of max basal',df_meal_basals_max)
    meal = df_meal_basals_max.basal_amt[0] # same as meal_basals_max
    change_time = df_meal_basals_max.date_time[0]
    delta = meal - prior
    return ( prior, meal, delta, change_time )

