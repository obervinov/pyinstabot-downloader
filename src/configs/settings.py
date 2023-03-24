"""
This module contains the system settings for this python project.
"""
import os

logger_level = os.environ.get(
    'LOGGER_LEVEL',
    'INFO'
)
bot_name = os.environ.get(
    'BOT_NAME',
    'pyinstabot-downloader'
)
storage_type = os.environ.get(
    'STORAGE_TYPE',
    'local'
)
temporary_dir = os.environ.get(
    'TEMPORARY_DIR',
    'tmp/'
)
vault_addr = os.environ.get(
    'BOT_VAULT_ADDR',
    'http://vault-server:8200'
)
vault_approle_id = os.environ.get(
    'BOT_VAULT_APPROLE_ID',
    'not set'
)
vault_approle_secret_id = os.environ.get(
    'BOT_VAULT_APPROLE_SECRET_ID',
    'not set'
)
instagram_session = os.environ.get(
    'BOT_INSTAGRAM_SESSION',
    '.session'
)
instagram_useragent = os.environ.get(
    'BOT_INSTAGRAM_USERAGENT',
    None
)
