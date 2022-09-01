use janice;

drop table if exists `User`;
CREATE TABLE `User` (
  `userId` int PRIMARY KEY AUTO_INCREMENT,
  `fullName` varchar(255) NOT NULL,
  `email` varchar(255) UNIQUE NOT NULL,
  `createdAt` datetime DEFAULT CURRENT_TIMESTAMP
);

insert into User(userId,fullName,email) values(7,'Hugh','hugh@hugh.com');

alter table insulin_carb_smoothed_2 add column userId int after user;

update insulin_carb_smoothed_2
set userId = 7 where user = 'Hugh';
