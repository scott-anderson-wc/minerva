-- Create table with 5hr clean regions for reverse engineering IAC

use janice;
DROP TABLE if exists clean_regions_5hr;
CREATE TABLE clean_regions_5hr (
    rtime datetime NOT NULL PRIMARY KEY, 
    bg0 integer,
    bg1 integer,
    bolus float
);
