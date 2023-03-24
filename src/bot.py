"""
This module contains the main code for the bot to work
and contains the main logic linking the extends modules.
"""
import time
import random
import datetime
from logger import log
from vault import VaultClient
from users import UsersAuth
from messages import Messages
from telegram import TelegramBot
from configs import settings
from extensions.downloader import Downloader
from extensions.uploader import Uploader

# vault client
vault_client = VaultClient(
    addr=settings.vault_addr,
    approle_id=settings.vault_approle_id,
    secret_id=settings.vault_approle_secret_id,
    mount_point=settings.bot_name
)

# telegram client
telegram_client = TelegramBot(settings.bot_name, vault_client)
telegram_bot = telegram_client.telegram_bot

# user auth module
users_auth = UsersAuth(vault_client, settings.bot_name)

# messages module
messages = Messages()

# downloader client
downloader_client = Downloader(
    auth={
        'sessionfile': settings.instagram_session
    },
    settings={
        'savepath': settings.temporary_dir,
        'useragent': settings.instagram_useragent
    }
)

# uploader client
uploader_client = Uploader(
    storage={
        'type': settings.storage_type,
        'temporary': settings.temporary_dir
    }
)



# Decorators
@telegram_bot.message_handler(commands=['start'])
def start_message(message: telegram_client.telegram_types.Message = None) -> None:
    """
    Function for intercepting the satrt command sent to the bot.

    :param message: The message received by the bot.
    :type message: telegram_client.telegram_types.Message
    :default message: None
    """
    if users_auth.check_permission(message.chat.id) == "allow":
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


@telegram_bot.message_handler(regexp=r"^https://(www\.)?instagram.com/(?!p/)(?!reel/).*$")
def get_posts_account(message):
    """
    A function for intercepting links sent to the bot to the Instagram profile.

    :param message: The message received by the bot.
    :type message: telegram_client.telegram_types.Message
    :default message: None
    """
    if users_auth.check_permission(message.chat.id) == "allow":
        account_name = message.text.split("/")[3].split("?")[0]
        log.info(
            '[%s] for url %s\n',
            __name__,
            message.text
        )
        account_info = downloader_client.get_download_info(account_name)
        telegram_bot.send_message(
            message.chat.id,
            messages.render_template(
                'account_info',
                account_name=account_name,
                shortcodes_count=account_info['shortcodes_total_count']
            )
        )
        editable_message = False
        stats_message_id = None

        for shortcode in account_info['shortcodes_for_download']:
            # download the contents of an instagram post to a temporary folder
            downloader_client.get_post_content(shortcode)
            # upload the received content to the destination storage
            uploader_client.prepare_content(shortcode)
            # render progressbar
            progressbar = messages.render_progressbar(
                account_info['shortcodes_total_count'],
                account_info['shortcodes_exist_count']
            )
            account_info['shortcodes_exist_count'] = account_info['shortcodes_exist_count'] + 1
            stats_response = messages.render_template(
                'account_stats_progress',
                account_name=account_name,
                posts_downloaded=account_info['shortcodes_exist_count'],
                posts_count=account_info['shortcodes_total_count'],
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

        # when all messages are uploaded send a response with statistics
        telegram_bot.edit_message_text(
            messages.render_template(
                'account_stats_done',
                posts_downloaded=account_info['shortcodes_exist_count'],
                posts_count=account_info['shortcodes_total_count'],
                account_name=account_name,
                progressbar=messages.render_progressbar(
                    account_info['shortcodes_total_count'],
                    account_info['shortcodes_exist_count']
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


@telegram_bot.message_handler(regexp="^https://www.instagram.com/(p|reel)/.*")
def get_post_account(message):
    """
    A function for intercepting links sent by a bot to an Instagram post.

    :param message: The message received by the bot.
    :type message: telegram_client.telegram_types.Message
    :default message: None
    """
    if users_auth.check_permission(message.chat.id) == "allow":
        shortcode = message.text.split("/")[4]
        log.info(
            '[%s] for url %s\n',
            __name__,
            message.text
        )
        # download the contents of an instagram post to a temporary folder
        dresponse = downloader_client.get_post_content(shortcode)
        # upload the received content to the destination storage
        ureposponse = uploader_client.prepare_content(shortcode)
        telegram_bot.send_message(
            message.chat.id,
            messages.render_template(
                'post_stats_info',
                download_response=dresponse,
                upload_response=ureposponse
            )
        )


def main():
    """
    The main function for launching telegram bot.
    """
    while True:
        log.info(
            'Starting telegram bot: %s\nVault: %s',
            settings.bot_name,
            settings.vault_addr
        )
        telegram_bot.polling()


if __name__ == "__main__":
    main()
