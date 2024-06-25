-- Important delta for loop logic

-- Rename some fields in realtime_cgm to match both
-- janice.realtime_cgm2 and loop_logic.source_cgm.

-- We will keep the cgm_id, however, as a comfort element, though
-- ultimately, I think we don't need it. Nevertheless, we'll add an
-- indexes for (user_id, rtime)

-- To keep the data, we'll create a temporary copy. This table is
-- defined identically to the original realtime_cgm:

DROP TABLE IF EXISTS `realtime_cgm_copy`;
CREATE TABLE `realtime_cgm_copy` (
  `cgm_id` int PRIMARY KEY AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `trend` int NOT NULL,
  `dexcom_timestamp_utc` datetime NOT NULL,
  `cgm_value` int NOT NULL
);
INSERT INTO `realtime_cgm_copy` select * from `realtime_cgm`;

-- Because of foreign key checks, I can't drop realtime_cgm, so I'm
-- going to borrow some code from mysqldump files:

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

-- The following definition is just like janice.realtime_cgm2 (see
-- sql/realtime_cgm.sql) *except* (1) we keep the cgm_id and make it
-- the primary key, (2) we drop the unneeded user column, and (3) we
-- drop the rtime column and the associated indexes.

drop table `realtime_cgm`;
CREATE TABLE `realtime_cgm` (
    cgm_id int PRIMARY KEY AUTO_INCREMENT,
    user_id int not null,
    -- user varchar(20),
    -- rtime datetime,
    dexcom_time datetime,
    mgdl smallint,
    trend tinyint,
    trend_code enum('None',     -- 0
               'DoubleUp',      -- 1
               'SingleUp',      -- 2
               'FortyFiveUp',   -- 3
               'Flat',          -- 4
               'FortyFiveDown', -- 5
               'SingleDown',    -- 6
               'DoubleDown',    -- 7
               'NotComputable', -- 8
               'RateOutOfRange' -- 9
               )
    -- primary key (user, rtime),
    -- index (user_id, rtime),
    -- index(rtime)
);

insert into `realtime_cgm`
select cgm_id, user_id, dexcom_timestamp_utc, cgm_value, trend, trend
from realtime_cgm_copy;


/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;
