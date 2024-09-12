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

# Vault Database Engine constants
VAULT_DBENGINE_MOUNT_POINT = f"{TELEGRAM_BOT_NAME}-database"
# Will be removed after https://github.com/obervinov/users-package/issues/47
VAULT_DB_ROLE_MAIN = f"{TELEGRAM_BOT_NAME}-bot"
VAULT_DB_ROLE_USERS = f"{TELEGRAM_BOT_NAME}-users"
VAULT_DB_ROLE_USERS_RL = f"{TELEGRAM_BOT_NAME}-users-rl"
