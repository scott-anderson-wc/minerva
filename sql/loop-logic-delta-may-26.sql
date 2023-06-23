-- Adding a real/fake field to loop_logic_test realtime_cgm, so that
-- we can be clear about when a test is being run.

-- also dropping the realtime_cgm_copy which we no longer need

-- use loop_logic_test;

alter table realtime_cgm add column `src` enum('real','fake');
