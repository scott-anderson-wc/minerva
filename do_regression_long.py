# sys.exit()

# the above model is a nice near-replication of the predictive model from October 2019

# Now, let's try to make a predictive model with a lag of two time steps. All we have to do
# is shift the good_bg column up one, drop the last row that now has a NaN value, and re-do
# the regression

bgdata['good_bg'] = bgdata['good_bg'].shift(-1)
bgdata.dropna()

y, X = dmatrices('good_bg ~ prev_bg + bg_slope + isf + di + di_slope', bgdata)

# model fitting
model = sm.OLS(y, X)            # describe model
res = model.fit()               # fit model
print((res.summary()))            # summarize model

# To try a lag of three time steps, we just shift again:

bgdata['good_bg'] = bgdata['good_bg'].shift(-1)
bgdata.dropna()

y, X = dmatrices('good_bg ~ prev_bg + bg_slope + isf + di + di_slope', bgdata)

# model fitting
model = sm.OLS(y, X)            # describe model
res = model.fit()               # fit model
print((res.summary()))            # summarize model

# To try a lag of four time steps, we just shift again:

bgdata['good_bg'] = bgdata['good_bg'].shift(-1)
bgdata.dropna()

y, X = dmatrices('good_bg ~ prev_bg + bg_slope + isf + di + di_slope', bgdata)

# model fitting
model = sm.OLS(y, X)            # describe model
res = model.fit()               # fit model
print((res.summary()))            # summarize model

# Last one: shift up 2 steps to get a 6-step lag:

bgdata['good_bg'] = bgdata['good_bg'].shift(-2)
bgdata.dropna()

y, X = dmatrices('good_bg ~ prev_bg + bg_slope + isf + di + di_slope', bgdata)

# model fitting
model = sm.OLS(y, X)            # describe model
res = model.fit()               # fit model
print((res.summary()))            # summarize model

