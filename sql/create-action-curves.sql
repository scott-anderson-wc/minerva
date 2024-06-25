-- see notes in action_curves.py and predictive_model_june21.py 

drop table if exists action_curves;
create table action_curves(
    uid int,
    kind enum('brunch','dinner','rescue','insulin'),
    curve_date timestamp,
    curve varchar(1000) comment 'the values on the curve as JSON. worst case: 8 chars/value * 12/hour * 6 hours = 576',
    notes text,
    primary key (uid, kind, curve_date)
);

describe action_curves;
