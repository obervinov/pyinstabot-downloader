"""
This module contains the constants for this python project.
"""
import os

# environment variables
LOGGER_LEVEL = os.environ.get(
    'LOGGER_LEVEL',
    'INFO'
)

BOT_NAME = os.environ.get(
    'BOT_NAME',
    'pyinstabot-downloader'
)

MESSAGES_CONFIG = os.environ.get(
    'MESSAGES_CONFIG',
    'src/configs/messages.json'
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

# permissions roles
POST_ROLE = 'get_post_role'
PROFILE_ROLE = 'get_profile_posts_role'
POSTS_LIST_ROLE = 'get_posts_list_role'
QUEUE_ROLE = 'get_queue_role'
HISTORY_ROLE = 'get_history_role'

# telegram buttons
TELEGRAM_STARTUP_BUTTONS = [
    "Post",
    "Posts List",
    "Profile Posts",
    "User's Queue",
    "User's History",
    "Clear Messages",
]

# Queue handler
QUEUE_FREQUENCY = 60
