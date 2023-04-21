-- These are gotten from the Parent Form ... spreadsheet that Janice sent:
-- this file should be idempotent.

-- use autoapp_test;

-- need to have Hugh in the system. 

insert into `user`(user_id, full_name, email) values(7, 'HughKB', 'hugh@domain.com')
on duplicate key update email = email;

-- this is the only configuration at the moment

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
        45                                  -- running_bolus_max
        );                                  

-- PK is the first field

replace into glucose_range_type_ref(glucose_range_type_id,glucose_range_type) values
(1, 'low'),
(2, 'in_range'),
(3, 'high');

-- glucose ranges. PK is first field, 2nd field is FK to glucose_range_type_ref, so this is defined after

replace into glucose_range(glucose_range_id,glucose_range_type_id,lower_bound,upper_bound)
values
(1,1,0,69),
(2,2,70,125),
(3,3,126,1000),
(4,1,0,72),
(5,2,73,130),
(6,3,131,1000);

-- two modes: night and day. range_ids are FK to glucose range, so this is defined after that

replace into mode(mode_id,name,user_id,is_active,is_default,low_range_id,in_range_id,high_range_id,cgm_target)
values
(1,'night',7,true,true,1,1,1,100),
(2,'day',7,false,false,2,2,2,100);

