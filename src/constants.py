"""
This module contains the constants for this python project.
"""
import os
from telegram import TelegramBot
from users import UsersAuth
from messages import Messages
from vault import VaultClient
from modules.downloader import Downloader
from modules.uploader import Uploader


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


# instances
VAULT_CLIENT = VaultClient(
    name=BOT_NAME
)

TELEGRAM_CLIENT = TelegramBot(
    vault=VAULT_CLIENT
)

BOT = TELEGRAM_CLIENT.telegram_bot

AUTH_CLIENT = UsersAuth(
    vault=VAULT_CLIENT
)

MESSAGES_GENERATOR = Messages(
    config_path=MESSAGES_CONFIG
)

DOWNLOADER_INSTANCE = Downloader(
    auth={
        'sessionfile': INSTAGRAM_SESSION
    },
    settings={
        'savepath': TEMPORARY_DIR,
        'useragent': INSTAGRAM_USERAGENT
    },
    vault=VAULT_CLIENT
)

UPLOADER_INSTANCE = Uploader(
    storage={
        'type': STORAGE_TYPE,
        'temporary': TEMPORARY_DIR,
        'cloud_root_path': BOT_NAME,
        'exclude_type': STORAGE_EXCLUDE_TYPE
    },
    vault=VAULT_CLIENT
)
