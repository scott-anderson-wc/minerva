/*
Create table for results of different nudge ISF computations
Schema version: 0
Author: Mileva Van Tuyl
*/

use janice;
DROP TABLE if exists nudge_isf_results;
CREATE TABLE nudge_isf_results (
    rtime datetime NOT NULL PRIMARY KEY, 
    clean_5_min float,
    clean_15_min float, 
    clean_30_min float,
    clean_2_hr float,
    clean_5_min_yrly_basal float,
    clean_15_min_yrly_basal float,
    clean_30_min_yrly_basal float,
    clean_2_hr_yrly_basal float
);
