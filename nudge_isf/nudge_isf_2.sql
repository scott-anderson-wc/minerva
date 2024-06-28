/*
Update the existing nudge_isf_results table to include additional columns for ISF computations
Schema version: 2
Author: Mileva Van Tuyl
*/

ALTER TABLE nudge_isf_results ADD clean_5_min_yrly_basal float;
ALTER TABLE nudge_isf_results ADD clean_15_min_yrly_basal float;
ALTER TABLE nudge_isf_results ADD clean_30_min_yrly_basal float;
ALTER TABLE nudge_isf_results ADD clean_2_hr_yrly_basal float;
