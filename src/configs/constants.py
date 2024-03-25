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

# permissions roles and buttons mapping
# 'button_title': 'role'
ROLES_MAP = {
    'Post': 'post',
    'Posts List': 'posts_list'
}

# Queue handler
QUEUE_FREQUENCY = 60
STATUSES_MESSAGE_FREQUENCY = 60
