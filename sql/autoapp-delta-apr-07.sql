-- delta for autoapp (and autoapp_test)

-- omitted the 'use' statement, so we can source this in both databases

-- Mattias uses snake_case so all fields converted to snake_case

CREATE TABLE `notification_history` (
    `notification_history_id` int PRIMARY KEY AUTO_INCREMENT,
    `user_id` int NOT NULL,
    -- the text message that is sent
    `payload` text NOT NULL,
    `notification_timestamp_utc` datetime DEFAULT CURRENT_TIMESTAMP,
    `user_devices` text,
    `follower_devices` text,
    foreign key (user_id) references accounts(user_id)
);
