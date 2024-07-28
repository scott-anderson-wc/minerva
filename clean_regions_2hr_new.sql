use janice;
DROP TABLE if exists clean_regions_2hr_new;
CREATE TABLE clean_regions_2hr_new (
    rtime datetime NOT NULL PRIMARY KEY, 
    bg0 integer,
    bg1 integer,
    bolus float, 
    isf float
);
