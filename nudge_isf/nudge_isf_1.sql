/*
Update the existing nudge_isf_results table to include additional columns for ISF computations
Schema version: 1
Author: Mileva Van Tuyl
*/

ALTER TABLE nudge_isf_results ADD clean_5_min float;
ALTER TABLE nudge_isf_results ADD clean_30_min float;
ALTER TABLE nudge_isf_results ADD clean_2_hr float;
