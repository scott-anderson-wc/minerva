-- Create table for testing the dynamic_carb computation

USE janice;
DROP TABLE if exists dynamic_carbs_test;
CREATE TABLE dynamic_carbs_test (
    rtime datetime NOT NULL,
    dynamic_carbs float DEFAULT NULL,
    PRIMARY KEY(rtime)
);
