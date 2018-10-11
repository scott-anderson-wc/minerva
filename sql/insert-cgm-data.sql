-- use the cgm_noduplicates table, which has already dealt with the grouping and disagreements of values

update insulin_carb_smoothed as ics inner join cgm_noduplicates as cgm using(rtime)
set ics.cgm = cgm.mgdl;
