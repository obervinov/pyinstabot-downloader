-- Schema for the users table
CREATE TABLE users (
    id serial PRIMARY KEY,
    user_id VARCHAR (50) UNIQUE NOT NULL,
    chat_id VARCHAR (50) NOT NULL,
    status VARCHAR (50) NOT NULL DEFAULT 'denied'
);

-- Schema for the users_requests table
CREATE TABLE users_requests (
    id serial PRIMARY KEY,
    user_id VARCHAR (50) NOT NULL,
    message_id VARCHAR (50),
    chat_id VARCHAR (50),
    authentication VARCHAR (50) NOT NULL,
    "authorization" VARCHAR (255) NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    rate_limits TIMESTAMP
);

-- Schema for queue table
CREATE TABLE queue (
    id serial PRIMARY KEY,
    user_id VARCHAR (50) NOT NULL,
    post_id VARCHAR (50) NOT NULL,
    post_url VARCHAR (255) NOT NULL,
    post_owner VARCHAR (50) NOT NULL,
    link_type VARCHAR (50) NOT NULL DEFAULT 'post',
    message_id VARCHAR (50) NOT NULL,
    chat_id VARCHAR (50) NOT NULL,
    scheduled_time TIMESTAMP NOT NULL,
    download_status VARCHAR (50) NOT NULL DEFAULT 'not started',
    upload_status VARCHAR (50) NOT NULL DEFAULT 'not started',
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    state VARCHAR (50) NOT NULL DEFAULT 'waiting'
);

-- Schema for the processed table
CREATE TABLE processed (
    id serial PRIMARY KEY,
    user_id VARCHAR (50) NOT NULL,
    post_id VARCHAR (50) NOT NULL,
    post_url VARCHAR (255) NOT NULL,
    post_owner VARCHAR (50) NOT NULL,
    link_type VARCHAR (50) NOT NULL DEFAULT 'post',
    message_id VARCHAR (50) NOT NULL,
    chat_id VARCHAR (50) NOT NULL,
    download_status VARCHAR (50) NOT NULL,
    upload_status VARCHAR (50) NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    state VARCHAR (50) NOT NULL DEFAULT 'processed'
);

-- Schema for the accounts table
CREATE TABLE accounts (
    id serial PRIMARY KEY,
    username VARCHAR (50) UNIQUE NOT NULL,
    pk VARCHAR (50) NOT NULL,
    full_name VARCHAR (50) NOT NULL,
    media_count INTEGER NOT NULL,
    follower_count INTEGER NOT NULL,
    following_count INTEGER NOT NULL,
    last_updated TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Schema for the migrations table
CREATE TABLE migrations (
    id serial PRIMARY KEY,
    name VARCHAR (255) NOT NULL,
    version VARCHAR (255) NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Schema for the messages table
CREATE TABLE messages (
    id serial PRIMARY KEY,
    message_id VARCHAR (50) NOT NULL,
    chat_id VARCHAR (50) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    message_type VARCHAR (50) NOT NULL,
    producer VARCHAR (50) NOT NULL,
    message_content_hash VARCHAR (64) NOT NULL,
    state VARCHAR (50) NOT NULL DEFAULT 'added'
);
