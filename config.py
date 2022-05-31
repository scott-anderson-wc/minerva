# version of the MD app
VERSION = '0.1.0'
MYSQL_CONNECT_DEBUG=True
MYSQL_CURSORCLASS='DictCursor'

# PM is for the paremeters configuring the Predictive Model

# These constants are options for where the ISF values come from

(PM_ISF_HISTORY_THEN_SMOOTHED,
 PM_ISF_SMOOTHED_ONLY) = (1, 2)

# This constant says which option to choose
PM_ISF_SOURCE = PM_ISF_HISTORY_THEN_SMOOTHED
