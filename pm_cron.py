'''Code to run the predictive model for right *now*, with logging to a
/home/hugh9/logfile and suitable for running via cron, with display in
a web page.

We'll run it every five minutes and recording the output in a
table. The front-end can poll that table to pull in the latest
predictive curve.

The prediction will be, for now, simply a series of predicted BG values. 

These will be converted to JSON and stored in a new database table:

Each trace will be 24 three-digit numbers, so the JSON string will be roughly:

len(json.dumps([ v+100 for v in range(24) ]))

which is 120. 


create table predictions(
    ptime datetime,     -- the time at which the prediction was made
    ptrace varchar(150), -- the JSON of the prediction
    di_trace varchar
    notes  varchar(100), -- the JSON list of notes
    primary key (ptime)
);

'''

import sys
import json
import datetime
import cs304dbi as dbi
import date_ui
import predictive_model_june21 as pm

def run_predictive_model(rtime):
    dbi.cache_cnf()
    conn = dbi.connect()
    pred_vals, di_vals, dc_vals, di_deltas, dc_deltas = pm.predictive_model_june21(rtime, conn=conn, debug=True)
    for v in [pred_vals, di_vals, dc_vals, di_deltas, dc_deltas]:
        x = json.dumps(pred_vals)
        print(len(x), x)


if __name__ == '__main__':
    run_predictive_model(date_ui.to_rtime(datetime.datetime.now()))
