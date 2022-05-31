--  March 2022.
--  Segun has created a web API for the Diamond data that
--  makes the rescue carbs available at
--  http://minervaanalysis.net/analytics/userCarbs?fromTimestamp=2022-01-02T13:56:55&userId=4

--  We want to copy that data over to the Janice database so that we can
--  include them in our predictive model.

--  That data looks like:

-- {"timestamp":"2022-01-02T22:23:15.000Z",
--    "carbName":"Juice box",
--    "quantity":1,
--    "carbCountGrams":15,
--    "totalCarbGrams":15,
--    "userId":4}

-- So, I've created a table to receive that data:

CREATE TABLE `rescue_carbs_from_diamond` (
  `user` tinyint NOT NULL,
  `timestamp` timestamp NOT NULL,
  `carbCountGrams` tinyint NOT NULL,
  `totalCarbGrams` tinyint NOT NULL,
  `quantity` tinyint NOT NULL,
  `carbName` varchar(30),
  --   PRIMARY KEY (user,timestamp)
  primary key (timestamp)
);
