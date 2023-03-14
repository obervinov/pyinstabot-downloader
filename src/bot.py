"""
This module contains the main code for the bot to work
and contains the main logic linking the extends modules.
"""
import os
from logger import log, logging
from vault import VaultClient
from users import UsersAuth
from messages import Messages
from telegram import TelegramBot
from extensions.downloader import Downlaoder


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
    instagram_save_path = storage_path
else:
    instagram_save_path = 'tmp/'
downloader_client = Downlaoder(
    instagram_user,
    instagram_pass,
    instagram_session,
    instagram_save_path,
    instagram_useragent
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


@telegram_bot.message_handler(regexp="^https://(www\.)?instagram.com/(?!p/)(?!reel/).*$")
def profile_get_posts(message):
    """
    A function for intercepting links sent to the bot to the Instagram profile.

    :param message: The message received by the bot.
    :type message: telegram_client.telegram_types.Message
    :default message: None
    """
    access_status = access_status = users_auth.check_permission(message.chat.id)
    if access_status == "success":
        profile_name = message.text.split("/")[3].split("?")[0]
        log.info(
            'Decorator.profile_get_posts() for url %s\nDecorator.profile_get_posts() Starting download posts for account %s',
            message.text,
            profile_name
        )
        
        instagram_client.download_all_posts(
                  profile_username,
                  ratelimit_timeout,
                  ratelimit_max_timeout,
                  message.chat.id
                  )
    else:
        log.error(
            '403: Forbidden for username %s',
            message.from_user.username
        )


# Download post per instagram-link by regex input text
@telegram_bot.message_handler(regexp="^https://www.instagram.com/(p|reel)/.*")
def profile_get_link_post(message):
    access_status = access_status = Users_auth.check_permission(message.chat.id)

    if access_status == "success":
        # Get shortcode value
        shortcode = str(message.text).split("/")[4]
        log.info("Decorator.profile_get_link_post() --> call Instagram.download_post()")
        response = Instagram.download_post(shortcode)
        telegram_bot.send_message(message.chat.id, response)

    else:
        log.error(f"403: Forbidden for username: {message.from_user.username}")


# Starting bot #
def main():
    while True:
        try:
            log.info(f"Starting telegram bot: {bot_name}")
            log.info(f"Home path: {os.getcwd()}")
            log.info(f"Vault: {vault_addr}")
            telegram_bot.polling()
        except Exception as ex:
            log.error(f"Strating telegram bot exception: {ex}")


if __name__ == "__main__":
    main()
