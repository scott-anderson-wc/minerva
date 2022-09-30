drop database if exists loop_logic;
create database loop_logic;
use loop_logic;

CREATE TABLE `RunState_REF` (
  `runStateId` int PRIMARY KEY AUTO_INCREMENT,
  `runState` ENUM ('awaitingFirstRun', 'regularRun', 'awaitingNewCycle', 'allRunsCompleted') NOT NULL
);

CREATE TABLE `BolusType_REF` (
  `bolusTypeId` int PRIMARY KEY AUTO_INCREMENT,
  `bolusType` ENUM ('loop', 'pump') NOT NULL
);

CREATE TABLE `Run` (
  `runId` int PRIMARY KEY AUTO_INCREMENT,
  `userId` int NOT NULL,
  `triggeredCgmId` int NOT NULL,
  `glucoseRangeId` int NOT NULL,
  `latestNotificationTimestamp` datetime DEFAULT CURRENT_TIMESTAMP,
  `currentRunStateId` int DEFAULT 0,
  `createdAt` datetime DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE `GlucoseRangeType_REF` (
  `glucoseRangeTypeId` int PRIMARY KEY AUTO_INCREMENT,
  `glucoseRangeType` ENUM ('low', 'inRange', 'high') NOT NULL
);

CREATE TABLE `GlucoseRange` (
  `glucoseRangeId` int PRIMARY KEY AUTO_INCREMENT,
  `gluoseRangeTypeId` int NOT NULL,
  `lowerBound` int NOT NULL,
  `upperBound` int NOT NULL,
  `bolusIntervalMins` int,
  `topupIntervalMins` int,
  `maxBolusIntervalMins` int,
  `singleBolusMax` int,
  `runningBolusMax` int,
  `significantNumber` int,
  `cgmTarget` int
);

CREATE TABLE `Mode` (
  `modeId` int PRIMARY KEY AUTO_INCREMENT,
  `name` varchar(255),
  `userId` int NOT NULL,
  `isActive` bool NOT NULL,
  `isDefault` bool NOT NULL,
  `lowRangeId` int NOT NULL,
  `inRangeId` int NOT NULL,
  `highRangeId` int NOT NULL
);

CREATE TABLE `User` (
  `userId` int PRIMARY KEY AUTO_INCREMENT,
  `fullName` varchar(255) NOT NULL,
  `email` varchar(255) UNIQUE NOT NULL,
  `createdAt` datetime DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE `LatestCgm` (
  `cgmId` int PRIMARY KEY AUTO_INCREMENT,
  `userId` int NOT NULL,
  `trend` int NOT NULL,
  `dexcomTimestampUtc` datetime NOT NULL,
  `cgmValue` int NOT NULL
);

CREATE TABLE `LoopBolus` (
  `LoopBolusId` int PRIMARY KEY AUTO_INCREMENT,
  `userId` int NOT NULL,
  `bolusValue` int NOT NULL,
  `bolusTypeId` int NOT NULL,
  `linkedCgmId` int NOT NULL,
  `commandId` int,
  `carbId` int,
  `bolusPumpId` int,
  `commandTimestamp` datetime,
  `bolusTimestamp` datetime,
  `settled` int,
  `anchor` int
);

CREATE TABLE `DateTimeProgram` (
  `dateTimeProgramId` int PRIMARY KEY AUTO_INCREMENT,
  `dateTimeProgramGuid` varchar(36) NOT NULL,
  `name` varchar(255) NOT NULL,
  `userId` int NOT NULL,
  `modeId` int NOT NULL,
  `isDefault` bool NOT NULL,
  `isActiveMonday` bool DEFAULT false,
  `isActiveTuesday` bool DEFAULT false,
  `isActiveWednesday` bool DEFAULT false,
  `isActiveThursday` bool DEFAULT false,
  `isActiveFriday` bool DEFAULT false,
  `isActiveSaturday` bool DEFAULT false,
  `isActiveSunday` bool DEFAULT false,
  `startTime` time NOT NULL,
  `endTime` time NOT NULL
);

CREATE UNIQUE INDEX `LatestCgm_index_0` ON `LatestCgm` (`userId`, `dexcomTimestampUtc`);

CREATE INDEX `LatestCgm_index_1` ON `LatestCgm` (`userId`);

CREATE INDEX `DateTimeProgram_index_2` ON `DateTimeProgram` (`modeId`);

CREATE INDEX `DateTimeProgram_index_3` ON `DateTimeProgram` (`userId`);

ALTER TABLE `Run` ADD FOREIGN KEY (`userId`) REFERENCES `User` (`userId`);

ALTER TABLE `Run` ADD FOREIGN KEY (`triggeredCgmId`) REFERENCES `LatestCgm` (`cgmId`);

ALTER TABLE `Run` ADD FOREIGN KEY (`glucoseRangeId`) REFERENCES `GlucoseRange` (`glucoseRangeId`);

ALTER TABLE `Run` ADD FOREIGN KEY (`currentRunStateId`) REFERENCES `RunState_REF` (`runStateId`);

ALTER TABLE `GlucoseRange` ADD FOREIGN KEY (`gluoseRangeTypeId`) REFERENCES `GlucoseRangeType_REF` (`glucoseRangeTypeId`);

ALTER TABLE `Mode` ADD FOREIGN KEY (`userId`) REFERENCES `User` (`userId`);

ALTER TABLE `Mode` ADD FOREIGN KEY (`lowRangeId`) REFERENCES `GlucoseRange` (`glucoseRangeId`);

ALTER TABLE `Mode` ADD FOREIGN KEY (`inRangeId`) REFERENCES `GlucoseRange` (`glucoseRangeId`);

ALTER TABLE `Mode` ADD FOREIGN KEY (`highRangeId`) REFERENCES `GlucoseRange` (`glucoseRangeId`);

ALTER TABLE `LatestCgm` ADD FOREIGN KEY (`userId`) REFERENCES `User` (`userId`);

ALTER TABLE `LoopBolus` ADD FOREIGN KEY (`userId`) REFERENCES `User` (`userId`);

ALTER TABLE `LoopBolus` ADD FOREIGN KEY (`bolusTypeId`) REFERENCES `BolusType_REF` (`bolusTypeId`);

ALTER TABLE `LoopBolus` ADD FOREIGN KEY (`linkedCgmId`) REFERENCES `LatestCgm` (`cgmId`);

ALTER TABLE `DateTimeProgram` ADD FOREIGN KEY (`userId`) REFERENCES `User` (`userId`);

ALTER TABLE `DateTimeProgram` ADD FOREIGN KEY (`modeId`) REFERENCES `Mode` (`modeId`);

-- ================================================================
-- The following table added by Scott, to keep track of migration of data from autoapp.

drop table if exists migration_status;
CREATE TABLE `migration_status` (
  `userId` int NOT NULL,
  `prev_update` datetime NOT NULL,
  `migration_time` datetime NOT NULL,
  PRIMARY KEY (`userId`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

-- Janice also wanted to keep a log, but I'll keep it separately
-- this omits a primary key, so we can log multiple things if they happen multiple times.
-- however, ideally, (user_id, prev_update) should be unique

-- These three datetimes should be in strictly increasing order

-- TODO: add FK constraint to an `accounts` table

drop table if exists migration_log;
create table `migration_log` (
  `userId` int NOT NULL,
  `prev_update` datetime NOT NULL,
  `last_update` datetime NOT NULL,
  `last_migration` datetime NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

alter table `migration_status` add foreign key (`userId`) references `User`(`userId`);
alter table `migration_log` add foreign key (`userId`) references `User`(`userId`);
