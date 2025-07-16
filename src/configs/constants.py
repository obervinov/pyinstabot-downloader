"""
This module contains the constants for this python project.
"""
import os

# environment variables
TELEGRAM_BOT_NAME = os.environ.get('TELEGRAM_BOT_NAME', 'pyinstabot-downloader')
TELEGRAM_BOT_VERSION = os.environ.get('TELEGRAM_BOT_VERSION', 'undefined')

# permissions roles and buttons mapping
# 'button_title': 'role'
ROLES_MAP = {
    'Posts': 'posts',
    'Account': 'account',
    'Reschedule Queue': 'reschedule_queue',
}

# Time intervals and ports (in seconds)
QUEUE_FREQUENCY = int(os.environ.get('TELEGRAM_BOT_QUEUE_FREQUENCY', 60))
STATUSES_MESSAGE_FREQUENCY = int(os.environ.get('TELEGRAM_BOT_STATUSES_MESSAGE_FREQUENCY', 15))
METRICS_PORT = int(os.environ.get('TELEGRAM_BOT_METRICS_PORT', 8000))
METRICS_INTERVAL = int(os.environ.get('TELEGRAM_BOT_METRICS_INTERVAL', 30))

# Vault Database Engine constants
VAULT_DB_ROLE = f"{TELEGRAM_BOT_NAME}"

# REGEX patterns
REGEX_SPECIFIC_LINK = r'^https://www\.instagram\.com/(p|reel)/.*'
REGEX_PROFILE_LINK = r'^https://www\.instagram\.com/.*'
