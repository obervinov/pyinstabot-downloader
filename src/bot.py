"""
This module contains the main code for the bot to work
and contains the main logic linking the extends modules.
"""
from logger import log
import constants


# Decorators
@constants.BOT.message_handler(commands=['start'])
def start_message(
    message: constants.TELEGRAM_CLIENT.telegram_types.Message = None
) -> None:
    """
    Function for intercepting the start command sent to the bot.

    Args:
        :param message (telegram_types.Message): the message received by the bot.

    Returns:
        None
    """
    if constants.AUTH_CLIENT.check_permissions(
        message.chat.id
    ) == "allow":
        log.info(
            '[%s] sending startup message in chat %s',
            __name__,
            message.chat.id
        )
        constants.BOT.send_message(
            message.chat.id,
            constants.MESSAGES_GENERATOR.render_template(
                'hello_message',
                username=message.from_user.username,
                userid=message.chat.id
            )
        )


@constants.BOT.message_handler(regexp=r"^https://(www\.)?instagram.com/(?!p/)(?!reel/).*$")
def get_posts_account(
     message: constants.TELEGRAM_CLIENT.telegram_types.Message = None
) -> None:
    """
    A function for intercepting links sent to the bot to the Instagram profile.

    Args:
        :param message (telegram_types.Message): the message received by the bot.

    Returns:
        None
    """
    if constants.AUTH_CLIENT.check_permissions(
        message.chat.id
    ) == "allow":
        log.info(
            '[%s] starting handler for url %s...',
            __name__,
            message.text
        )

        account_name = message.text.split("/")[3].split("?")[0]
        account_info = constants.DOWNLOADER_INSTANCE.get_download_info(
            account=account_name
        )
        editable_message = False
        stats_message_id = None

        constants.BOT.send_message(
            message.chat.id,
            constants.MESSAGES_GENERATOR.render_template(
                'account_info',
                account_name=account_name,
                shortcodes_count=account_info['shortcodes_total_count']
            )
        )

        for shortcode in account_info['shortcodes_for_download']:
            # download the contents of an instagram post to a temporary folder
            d_response = constants.DOWNLOADER_INSTANCE.get_post_content(
                shortcode
            )
            # upload the received content to the destination storage
            _ = constants.UPLOADER_INSTANCE.start_upload(
                d_response['owner']
            )
            # render progressbar
            progressbar = constants.MESSAGES_GENERATOR.render_progressbar(
                account_info['shortcodes_total_count'],
                account_info['shortcodes_exist_count']
            )
            account_info['shortcodes_exist_count'] = account_info['shortcodes_exist_count'] + 1
            stats_response = constants.MESSAGES_GENERATOR.render_template(
                'account_stats_progress',
                account_name=account_name,
                posts_downloaded=account_info['shortcodes_exist_count'],
                posts_count=account_info['shortcodes_total_count'],
                progressbar=progressbar
            )
            # check whether a message with stats has already been sent and whether we can edit it
            if not editable_message:
                stats_message_id = constants.BOT.send_message(
                    message.chat.id,
                    stats_response
                ).id
                editable_message = True
            elif editable_message:
                constants.BOT.edit_message_text(
                    stats_response,
                    message.chat.id,
                    stats_message_id
                )

        # when all messages are uploaded send a response with statistics
        constants.BOT.edit_message_text(
            constants.MESSAGES_GENERATOR.render_template(
                'account_stats_done',
                posts_downloaded=account_info['shortcodes_exist_count'],
                posts_count=account_info['shortcodes_total_count'],
                account_name=account_name,
                progressbar=constants.MESSAGES_GENERATOR.render_progressbar(
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


@constants.BOT.message_handler(regexp="^https://www.instagram.com/(p|reel)/.*")
def get_post_account(
     message: constants.TELEGRAM_CLIENT.telegram_types.Message = None
) -> None:
    """
    A function for intercepting links sent by a bot to an Instagram post.

    Args:
        :param message (telegram_types.Message): the message received by the bot.

    Returns:
        None
    """
    if constants.AUTH_CLIENT.check_permissions(
        message.chat.id
    ) == "allow":
        log.info(
            '[%s] starting handler for url %s...',
            __name__,
            message.text
        )

        shortcode = message.text.split("/")[4]
        # check history downloaded
        for owner in constants.VAULT_CLIENT.list_secrets(path='history/'):
            for post in constants.VAULT_CLIENT.read_secret(path=f"history/{owner}"):
                if post == shortcode and constants.VAULT_CLIENT.read_secret(
                    path=f"history/{owner}",
                    key=post
                ) == 'downloaded':
                    constants.BOT.send_message(
                        message.chat.id,
                        constants.MESSAGES_GENERATOR.render_template(
                            'post_already_downloaded',
                            post_id=shortcode,
                            owner=owner
                        )
                    )
                    log.warning(
                        '[%s] the post %s of the owner %s has already been downloaded, skipped.',
                        __name__,
                        post,
                        owner
                    )
                    return
        # download the contents of an instagram post to a temporary folder
        d_response = constants.DOWNLOADER_INSTANCE.get_post_content(
            shortcode
        )
        # upload the received content to the destination storage
        u_response = constants.UPLOADER_INSTANCE.start_upload(
            d_response['owner']
        )
        constants.BOT.send_message(
            message.chat.id,
            constants.MESSAGES_GENERATOR.render_template(
                'post_stats_info',
                post_id=shortcode,
                download_response=d_response,
                upload_response=u_response
            )
        )


def main():
    """
    The main function for launching telegram bot.

    Args:
        None

    Returns:
        None
    """
    while True:
        log.info(
            'Starting telegram bot %s',
            constants.BOT_NAME
        )
        constants.BOT.polling()


if __name__ == "__main__":
    main()
