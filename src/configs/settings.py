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
instagram_session = os.environ.get(
    'INSTAGRAM_SESSION',
    '.session'
)
instagram_useragent = os.environ.get(
    'INSTAGRAM_USERAGENT',
    None
)
