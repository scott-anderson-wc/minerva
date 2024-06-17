/*
Create table for results of different nudge ISF computations
Schema version: 0
Author: Mileva Van Tuyl
*/

use janice;
DROP TABLE if exists nudge_isf_results;
CREATE TABLE nudge_isf_results (
    rtime datetime NOT NULL PRIMARY KEY, 
    clean_15_min float     
);
