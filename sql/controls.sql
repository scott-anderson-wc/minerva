use janice;

-- This table will presumably always have exactly one row. It acts
-- as a set of global parameters, editable via PHPMyAdmin

drop table if exists controls;
create table controls(
    cgm_source enum('dexcom', 'libre')
);

-- initial settings
insert into controls values('dexcom');
