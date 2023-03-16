"""
This module contains the main code for the bot to work
and contains the main logic linking the extends modules.
"""
import os
import time
import random
import datetime
from logger import log, logging
from vault import VaultClient
from users import UsersAuth
from messages import Messages
from telegram import TelegramBot
from extensions.downloader import Downloader


# Environment variables
bot_name = os.environ.get(
    'BOT_NAME',
    'pyinstabot-downloader'
)
storage_type = os.environ.get(
    'STORAGE_TYPE',
    'local'
)
storage_path = os.environ.get(
    'STORAGE_PATH',
    None
)
vault_mount_point = os.environ.get(
    'BOT_VAULT_MOUNT_PATH',
    'secretv2'
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
    'instaloader/.session'
)
instagram_useragent = os.environ.get(
    'BOT_INSTAGRAM_USERAGENT',
    None
)


# Create instances of classes
## vault client
vault_client = VaultClient(
    vault_addr,
    vault_approle_id,
    vault_approle_secret_id,
    vault_mount_point
)

## telegram client
telegram_client = TelegramBot(bot_name, vault_client)
telegram_bot = telegram_client.telegram_bot

## user auth module
users_auth = UsersAuth(vault_client, bot_name)

## messages module
messages = Messages()

## instagram client
instagram_user = vault_client.vault_read_secrets(f"{bot_name}-config/config", "i_user")
instagram_pass = vault_client.vault_read_secrets(f"{bot_name}-config/config", "i_pass")
if storage_type == "local":
    INSTAGRAM_SAVEPATH = storage_path
else:
    INSTAGRAM_SAVEPATH = 'tmp/'
downloader_client = Downloader(
    auth={
        'username': instagram_user,
        'password': instagram_pass,
        'sessionfile': instagram_session,
    },
    settings={
        'savepath': INSTAGRAM_SAVEPATH,
        'useragent': instagram_useragent
    }
)

## Logger handler
logging.getLogger('bot.bot').setLevel(logging.INFO)
log.debug(globals())


# Decorators
@telegram_bot.message_handler(commands=['start'])
def start_message(message: telegram_client.telegram_types.Message = None) -> None:
    """
    Function for intercepting the satrt command sent to the bot.

    :param message: The message received by the bot.
    :type message: telegram_client.telegram_types.Message
    :default message: None
    """
    access_status = users_auth.check_permission(message.chat.id)
    if access_status == "success":
        log.info(
            '[%s] sending startup message in chat %s',
            __name__,
            message.chat.id
        )
        telegram_bot.send_message(
            message.chat.id,
            messages.render_template(
                'hello_message',
                username=message.from_user.username
            )
        )
    else:
        log.error(
            '403: Forbidden for username %s',
            message.from_user.username
        )


@telegram_bot.message_handler(regexp=r"^https://(www\.)?instagram.com/(?!p/)(?!reel/).*$")
def get_posts_account(message):
    """
    A function for intercepting links sent to the bot to the Instagram profile.

    :param message: The message received by the bot.
    :type message: telegram_client.telegram_types.Message
    :default message: None
    """
    access_status = access_status = users_auth.check_permission(message.chat.id)
    if access_status == "success":
        account_name = message.text.split("/")[3].split("?")[0]
        log.info(
            'Decorator.get_posts_account() for url %s\n',
            message.text
        )
        account_info = downloader_client.get_download_info(account_name)
        telegram_bot.send_message(
            message.chat.id,
            messages.render_template(
                'account_info',
                account_name=account_name,
                shortcodes_count=account_info['shortcodes_count']
            )
        )
        editable_message = False
        stats_message_id = None
        for shortcode in account_info['shortcodes_for_download']:
            downloader_client.get_post_content(shortcode)
            progressbar = messages.render_progressbar(
                account_info['shortcodes_count'],
                account_info['shortcodes_exist']
            )
            posts_downloaded = len(
                vault_client.vault_read_secrets(f"{bot_name}-data/{account_name}").keys()
            )
            stats_response = messages.render_template(
                'account_stats_progress',
                account_name=account_name,
                posts_downloaded=posts_downloaded,
                posts_count=account_info['shortcodes_count'],
                progressbar=progressbar
            )
            # check whether a message with stats has already been sent and whether we can edit it
            if not editable_message:
                stats_message_id = telegram_bot.send_message(
                    message.chat.id,
                    stats_response
                ).id
                editable_message = True
            elif editable_message:
                telegram_bot.edit_message_text(
                    stats_response,
                    message.chat.id,
                    stats_message_id
                )
            # pause downloaded for ratelimit
            log.warning(
                '[%s] ratelimit aplied at %s',
                __name__,
                datetime.datetime.now().strftime('%H:%M:%S')
            )
            time.sleep(random.randrange(1, 3000, 10))
        telegram_bot.edit_message_text(
            messages.render_template(
                'account_stats_done',
                posts_downloaded=posts_downloaded,
                posts_count=account_info['shortcodes_count'],
                account_name=account_name,
                progressbar=messages.render_progressbar(
                    account_info['shortcodes_count'],
                    posts_downloaded
                )
            ),
            message.chat.id,
            stats_message_id
        )
        log.info(
            '[%s] all available posts from account %s has been downloaded',
            __name__,
            account_name
        )
    else:
        log.error(
            '403: Forbidden for username %s',
            message.from_user.username
        )


@telegram_bot.message_handler(regexp="^https://www.instagram.com/(p|reel)/.*")
def get_post_account(message):
    """
    A function for intercepting links sent by a bot to an Instagram post.

    :param message: The message received by the bot.
    :type message: telegram_client.telegram_types.Message
    :default message: None
    """
    access_status = access_status = users_auth.check_permission(message.chat.id)
    if access_status == "success":
        shortcode = message.text.split("/")[4]
        log.info(
            'Decorator.get_post_account() for url %s\n',
            message.text
        )
        download_response = downloader_client.get_post_content(shortcode)
        telegram_bot.send_message(
            message.chat.id,
            messages.render_template(
                'post_stats_info',
                download_response=download_response,
                upload_response=upload_response
            )
        )
    else:
        log.error(
            '403: Forbidden for username %s',
            message.from_user.username
        )


def main():
    """
    The main function for launching telegram bot.
    """
    while True:
        log.info(
            'Starting telegram bot: %s\nHome path: %s\nVault: %s',
            bot_name,
            os.getcwd(),
            vault_addr
        )
        telegram_bot.polling()


if __name__ == "__main__":
    main()
