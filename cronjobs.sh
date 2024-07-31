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

# the crontab entry should look like
# * * * * /home/hugh9/scott/prod3/minerva/cronjobs.sh 
# and let the error output go to email

devel=/home/hugh9/scott/devel3
prod=/home/hugh9/scott/prod3/

if [ "$PWD" = "$devel" ]; then
    echo "running the development versions, output to terminal"
    python="$devel/venv369/bin/python3"
    repo="$devel"
else
    python="$prod/venv369/bin/python3"
    repo="$prod/minerva"
fi

if [ ! -x "$python" ]; then
    echo "cannot find python $python "
    exit
fi

if [ ! -d "$repo" ]; then
   echo "cannot find repo directory $repo "
fi

# Need to be *in* the $repo directory. When this runs
# as a cron job, it runs in the home directory
cd $repo

$python dexcom_cgm_sample.py 

# as of July 31, 2024, this seems to be working
# needs to be before the autoapp job
$python pull_data_from_diamon.py

# 'cron' is actually the default, so it's not necessary
$python autoapp_to_ics2.py cron 

# $python $repo/autoapp_to_loop_logic.py
$python autoapp_to_loop_logic_inputs.py 
$python loop_logic_testing_cgm_cron.py
