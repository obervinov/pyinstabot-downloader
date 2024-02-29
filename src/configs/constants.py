"""
This module contains the constants for this python project.
"""
import os

# environment variables
PROJECT_ENVIRONMENT = os.environ.get(
    "PROJECT_ENVIRONMENT",
    "dev"
)

TELEGRAM_BOT_NAME = os.environ.get(
    'TELEGRAM_BOT_NAME',
    'pyinstabot-downloader'
)

STORAGE_TYPE = os.environ.get(
    'STORAGE_TYPE',
    'mega'
)

TEMPORARY_DIR = os.environ.get(
    'TEMPORARY_DIR',
    'tmp/'
)

INSTAGRAM_SESSION = os.environ.get(
    'INSTAGRAM_SESSION',
    '.session'
)

INSTAGRAM_USERAGENT = os.environ.get(
    'INSTAGRAM_USERAGENT',
    None
)

STORAGE_EXCLUDE_TYPE = os.environ.get(
    'STORAGE_EXCLUDE_TYPE',
    '.txt'
)

# permissions roles and buttons mapping
# 'button_title': 'role'
ROLES_MAP = {
    'Post': 'post',
    'Posts List': 'posts_list',
    'Profile Posts': 'profile_posts',
    'User Queue': 'user_queue',
    'Clear Messages': 'clear_messages',
}

# Queue handler
QUEUE_FREQUENCY = 60
