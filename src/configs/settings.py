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
    'VAULT_ADDR',
    'http://vault-server:8200'
)
vault_approle_id = os.environ.get(
    'VAULT_APPROLE_ID',
    None
)
vault_approle_secret_id = os.environ.get(
    'VAULT_APPROLE_SECRET_ID',
    None
)
instagram_session = os.environ.get(
    'INSTAGRAM_SESSION',
    '.session'
)
instagram_useragent = os.environ.get(
    'INSTAGRAM_USERAGENT',
    None
)
