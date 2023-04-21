set @dt = '2022-12-01 1:30';

PREPARE stmt1 FROM
'SELECT min(abs(time_to_sec(timediff(date, ?)))) 
         FROM (SELECT date 
               FROM autoapp.bolus 
               WHERE user_id = 7 
               AND date BETWEEN (? - interval 30 minute) and (? + interval 30 minute))
            AS near
';
EXECUTE stmt1 USING @dt, @dt, @dt;


PREPARE stmt2 FROM
'SELECT bolus_id, user_id, date, type, value, duration, server_date 
 FROM autoapp.bolus
 WHERE abs(time_to_sec(timediff(date, ?))) = 
       (SELECT min(abs(time_to_sec(timediff(date, ?)))) 
         FROM (SELECT date 
               FROM autoapp.bolus 
               WHERE user_id = 7 
               AND date BETWEEN (? - interval 30 minute) and (? + interval 30 minute)) 
            AS near)

';

EXECUTE stmt2 USING @dt, @dt, @dt, @dt;


