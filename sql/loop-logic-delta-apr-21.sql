-- More deltas for Loop logic

-- omitted the 'use' statement, so we can source this in both loop_logic and loop_logic_test

-- use loop_logic;

alter table configuration add `carb_interval_mins` integer;

replace into configuration values(
        1,                      -- configuration_id
        7,                      -- user_id
        20,20,40,40,50,50,50,50,50,40,40,20, -- isf values
        10,                                  -- significant_cgm_value
        40,                                  -- command_timeout_mins
        20,                                  -- no_pump_data_interval
        20,                                  -- no_cgm_data_interval
        30,                                  -- awaiting_new_cycle_interval
        10,                                  -- time_delay_hybrid_control
        120,                                  -- bolus_interval_mins defines anchor bolus
        30,                                  -- topup_interval_mins
        240,                                  -- max_bolus_interval_mins
        15,                                  -- single_bolus_max
        45,                                  -- running_bolus_max
        30                                  -- carb_interval_mins
        );                                  

-- Also, all the integer fields are storing just 0/1. So we should make them tinyint.

