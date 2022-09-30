#!/bin/bash

# We're accumulating a lot of cron jobs. To keep them separate makes
# sense for coding, but running them all at the five minute mark runs
# the risk that they will interfere with each other. Instead, we'll
# run them serially in this script, which we can easily test by hand,
# and capture the stdout and sterr output in log files (in additiona
# to whatever custom logging each app does).

# this script runs code in the production directory, unless the CWD in
# the development directory

# We should probably just have a single venv version of python

devel=/home/hugh9/scott/devel3
prod=/home/hugh9/scott/prod3/

if [ "$PWD" = "$devel" ]; then
    echo "running the development versions, output to terminal"
    logfile=/dev/stdout
    python="$devel/venv369/bin/python3"
    repo="$devel"
else
    logfile=/home/hugh9/cronjobs.log
    python="$prod/venv369/bin/python3"
    repo="$prod/minerva"
fi

if [ ! -x "$python" ]; then
    echo "cannot find python $python " >> $logfile
    exit
fi

if [ ! -d "$repo" ]; then
   echo "cannot find repo directory $repo " >> $logfile
fi

# $python $repo/dexcom_cgm_sample.py > $logfile 2&>1
# $python $repo/autoapp_to_ics2.py cron > $logfile 2&>1
$python $repo/autoapp_to_loop_logic.py > $logfile 2&>1
