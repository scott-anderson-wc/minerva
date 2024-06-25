-- Removing the NOT NULL to these two fields, otherwise the default value is the first value, which makes no sense.

use loop_logic;

alter table loop_summary modify column
  `state` ENUM ('pending', 'abort', 'created', 'read', 'sent', 'done', 'error', 'timeout', 'canceled');
alter table loop_summary modify column
  `type` ENUM ('profile', 'suspend', 'temporary_basal', 'bolus', 'dual_bolus', 'extended_bolus', 'cancel_temporary_basal');

use loop_logic_test;

alter table loop_summary modify column
  `state` ENUM ('pending', 'abort', 'created', 'read', 'sent', 'done', 'error', 'timeout', 'canceled');
alter table loop_summary modify column
  `type` ENUM ('profile', 'suspend', 'temporary_basal', 'bolus', 'dual_bolus', 'extended_bolus', 'cancel_temporary_basal');

