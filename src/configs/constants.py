"""
This module contains the constants for this python project.
"""
import os

# environment variables
TELEGRAM_BOT_NAME = os.environ.get('TELEGRAM_BOT_NAME', 'pyinstabot-downloader')

# permissions roles and buttons mapping
# 'button_title': 'role'
ROLES_MAP = {
    'Post': 'post',
    'Posts List': 'posts_list',
    'Reschedule Queue': 'reschedule_queue',
}

# Queue handler
QUEUE_FREQUENCY = 60
STATUSES_MESSAGE_FREQUENCY = 15
METRICS_PORT = 8000
METRICS_INTERVAL = 30
