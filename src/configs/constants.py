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

# Other constants
QUEUE_FREQUENCY = 60
STATUSES_MESSAGE_FREQUENCY = 15
METRICS_PORT = 8000
METRICS_INTERVAL = 30

# Vault Database Engine constants
VAULT_DBENGINE_MOUNT_POINT = f"{TELEGRAM_BOT_NAME}-database"
VAULT_DB_ROLE = f"{TELEGRAM_BOT_NAME}"
