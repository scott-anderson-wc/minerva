'''Script to use statsmodel, pandas and patsy to convert a TSV file to a regression model.

Scott D. Anderson
6/12/2020
'''

import sys
import statsmodels.api as sm
import pandas

from patsy import dmatrices

import eval_model as em

# ================================================================

# tab separator, names on first line (default)
bgdata = pandas.read_csv('regression_table.tsv', sep='\t')

# create design matrices using R syntax. This says we want to predict
# good_bg as a linear function of the listed predictor variables

y, X = dmatrices('good_bg ~ prev_bg + bg_slope + isf + di + di_slope', bgdata)

# model fitting
model = sm.OLS(y, X)            # describe model
res = model.fit()               # fit model
print((res.summary()))            # summarize model

print('================================================================')
print('pos, neg, variance, std_dev, n')
print((em.eval_model(res.params, bgdata))) # run it and see how good it is

