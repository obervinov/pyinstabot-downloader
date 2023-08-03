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
messages_config = os.environ.get(
    'MESSAGES_CONFIG',
    'src/configs/messages.json'
)
storage_type = os.environ.get(
    'STORAGE_TYPE',
    'local'
)
temporary_dir = os.environ.get(
    'TEMPORARY_DIR',
    'tmp/'
)
instagram_session = os.environ.get(
    'INSTAGRAM_SESSION',
    '.session'
)
instagram_useragent = os.environ.get(
    'INSTAGRAM_USERAGENT',
    None
)
storage_exclude_type = os.environ.get(
    'STORAGE_EXCLUDE_TYPE',
    '.txt'
)
# For logging vault addr
vault_addr = os.environ.get(
    'VAULT_ADDR',
    None
)
