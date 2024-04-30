"""
This module contains the main code for the bot
to work and contains the main logic linking the additional modules.
"""
from datetime import datetime, timedelta
import re
import threading
import time
import random
import string

from mock import MagicMock
from logger import log
from telegram import TelegramBot
from users import Users
from vault import VaultClient
# pylint: disable=unused-import
# flake8: noqa
from configs.constants import (
    PROJECT_ENVIRONMENT, TELEGRAM_BOT_NAME, ROLES_MAP,
    QUEUE_FREQUENCY, STATUSES_MESSAGE_FREQUENCY
)
from modules.database import DatabaseClient
from modules.exceptions import FailedMessagesStatusUpdater
from modules.tools import get_hash
from modules.downloader import Downloader
from modules.uploader import Uploader



# Vault client
vault = VaultClient(name=TELEGRAM_BOT_NAME)
# Telegram instance
telegram = TelegramBot(vault=vault)
# Telegram bot for decorators
bot = telegram.telegram_bot
# Users module with rate limits option
users_rl = Users(vault=vault)
# Users module without rate limits option
users = Users(vault=vault, rate_limits=False)

# Client for download content from supplier
# If API disabled, the mock object will be used
downloader_api_enabled = bool(vault.read_secret(path='configuration/downloader-api').get('enabled', False))
if downloader_api_enabled is True:
    downloader = Downloader(vault=vault)
else:
    log.warning('[Bot]: Downloader API is disabled, using mock object, because enabled flag is %s', downloader_api_enabled)
    downloader = MagicMock()
    downloader.get_post_content.return_value = {
        'post': f"mock_{''.join(random.choices(string.ascii_letters + string.digits, k=10))}",
        'owner': 'undefined',
        'type': 'fake',
        'status': 'completed'
    }

# Client for upload content to the cloud storage
# If API disabled, the mock object will be used
uploader_api_enabled = bool(vault.read_secret(path='configuration/uploader-api').get('enabled', False))
if uploader_api_enabled is True:
    uploader = Uploader(vault=vault)
else:
    log.warning('[Bot]: Uploader API is disabled, using mock object, because enabled flag is %s', uploader_api_enabled)
    uploader = MagicMock()
    uploader.run_transfers.return_value = 'completed'

# Client for communication with the database
database = DatabaseClient(vault=vault, environment=PROJECT_ENVIRONMENT)


# START HANDLERS BLOCK ##############################################################################################################
# Command handler for START command
@bot.message_handler(commands=['start'])
def start_command(message: telegram.telegram_types.Message = None) -> None:
    """
    Sends a startup message to the specified Telegram chat.

    Args:
        message (telegram.telegram_types.Message): The message object containing information about the chat.

    Returns:
        None
    """
    if users.user_access_check(message.chat.id).get('access', None) == users.user_status_allow:
        log.info('[Bot]: Processing `start` command for user %s...', message.chat.id)

        # Add user to the database
        _ = database.add_user(user_id=message.chat.id, chat_id=message.chat.id)

        # Main message
        reply_markup = telegram.create_inline_markup(ROLES_MAP.keys())
        start_message = telegram.send_styled_message(
            chat_id=message.chat.id,
            messages_template={
                'alias': 'start_message',
                'kwargs': {'username': message.from_user.username, 'userid': message.chat.id}
            },
            reply_markup=reply_markup
        )
        bot.pin_chat_message(start_message.chat.id, start_message.id)
        bot.delete_message(message.chat.id, message.id)
        update_status_message(user_id=message.chat.id)
    else:
        telegram.send_styled_message(
            chat_id=message.chat.id,
            messages_template={
                'alias': 'reject_message',
                'kwargs': {'username': message.chat.username, 'userid': message.chat.id}
            }
        )


# Callback query handler for InlineKeyboardButton (BUTTONS)
@bot.callback_query_handler(func=lambda call: True)
def bot_callback_query_handler(call: telegram.callback_query = None) -> None:
    """
    The handler for the callback query from the user.
    Mainly used to handle button presses.

    Args:
        call (telegram.callback_query): The callback query object.

    Returns:
        None
    """
    log.info('[Bot]: Processing button %s for user %s...', call.data, call.message.chat.id)
    if users.user_access_check(call.message.chat.id, ROLES_MAP[call.data]).get('permissions', None) == users.user_status_allow:
        if call.data == "Post":
            button_post(call=call)
        elif call.data == "Posts List":
            button_posts_list(call=call)
        else:
            log.error('[Bot]: Handler for button %s not found', call.data)
    else:
        telegram.send_styled_message(
            chat_id=call.message.chat.id,
            messages_template={
                'alias': 'permission_denied_message',
                'kwargs': {'username': call.message.chat.username, 'userid': call.message.chat.id}
            }
        )


# Handler for incorrect flow (UNKNOWN INPUT)
@bot.message_handler(regexp=r'.*')
def unknown_command(message: telegram.telegram_types.Message = None) -> None:
    """
    Sends a message to the user if the command is not recognized.

    Args:
        message (telegram.telegram_types.Message): The message object containing the unrecognized command.

    Returns:
        None
    """
    if users.user_access_check(message.chat.id).get('access', None) == users.user_status_allow:
        log.error('[Bot]: Invalid command `%s` from user %s', message.text, message.chat.id)
        telegram.send_styled_message(
            chat_id=message.chat.id,
            messages_template={'alias': 'unknown_command'}
        )
    else:
        telegram.send_styled_message(
            chat_id=message.chat.id,
            messages_template={
                'alias': 'reject_message',
                'kwargs': {'username': message.chat.username, 'userid': message.chat.id}
            }
        )
# END HANDLERS BLOCK ##############################################################################################################


# START BUTTONS BLOCK #############################################################################################################
# Inline button handler for Post
def button_post(call: telegram.callback_query = None) -> None:
    """
    The handler for the Post button.

    Args:
        call (telegram.callback_query): The callback query object.

    Returns:
        None
    """
    user = users.user_access_check(call.message.chat.id, ROLES_MAP['Post'])
    if user.get('permissions', None) == users.user_status_allow:
        help_message = telegram.send_styled_message(
            chat_id=call.message.chat.id,
            messages_template={'alias': 'help_for_post'}
        )
        bot.register_next_step_handler(
            call.message,
            process_one_post,
            help_message
        )
    else:
        telegram.send_styled_message(
            chat_id=call.message.chat.id,
            messages_template={
                'alias': 'permission_denied_message',
                'kwargs': {'username': call.message.chat.username, 'userid': call.message.chat.id}
            }
        )


# Inline button handler for Posts List
def button_posts_list(call: telegram.callback_query = None) -> None:
    """
    The handler for the Posts List button.

    Args:
        call (telegram.callback_query): The callback query object.

    Returns:
        None
    """
    user = users.user_access_check(call.message.chat.id, ROLES_MAP['Posts List'])
    if user.get('permissions', None) == users.user_status_allow:
        help_message = telegram.send_styled_message(
            chat_id=call.message.chat.id,
            messages_template={'alias': 'help_for_posts_list'}
        )
        bot.register_next_step_handler(
            call.message,
            process_list_posts,
            help_message
        )
    else:
        telegram.send_styled_message(
            chat_id=call.message.chat.id,
            messages_template={
                'alias': 'permission_denied_message',
                'kwargs': {'username': call.message.chat.username, 'userid': call.message.chat.id}
            }
        )


# START BLOCK ADDITIONAL FUNCTIONS ######################################################################################################
def update_status_message(
    user_id: str = None
) -> None:
    """
    Updates the status message for the user.

    Args:
        user_id (str): The user id.

    Returns:
        None
    """
    try:
        chat_id = user_id
        exist_status_message = database.get_considered_message(message_type='status_message', chat_id=chat_id)
        message_statuses = get_message_statuses(user_id=user_id)
        diff_between_messages = False
        if exist_status_message:
            # check difference between messages content
            if exist_status_message[3] != get_hash(message_statuses):
                diff_between_messages = True

            # if message already sended and expiring (because bot can edit message only first 48 hours)
            # automatic renew message every 23 hours
            if exist_status_message[2] < datetime.now() - timedelta(hours=23):
                if exist_status_message[2] < datetime.now() - timedelta(hours=48):
                    log.warning('[Bot]: Message with type `status_message` for user %s old more than 48 hours, can not delete them', user_id)
                else:
                    _ = bot.delete_message(
                        chat_id=chat_id,
                        message_id=exist_status_message[0]
                    )
                status_message = telegram.send_styled_message(
                    chat_id=chat_id,
                    messages_template={
                        'alias': 'message_statuses',
                        'kwargs': message_statuses
                    }
                )
                database.keep_message(
                    message_id=status_message.message_id,
                    chat_id=status_message.chat.id,
                    message_type='status_message',
                    message_content=message_statuses
                )
                log.info('[Bot]: Message with type `status_message` for user %s has been renewed', user_id)
            elif message_statuses is not None and diff_between_messages:
                log.info(
                    '[Bot]: Message with type `status_message` for user %s is outdated (old: %s, new: %s), updating...',
                    user_id, exist_status_message[3], get_hash(message_statuses)
                )
                editable_message = telegram.send_styled_message(
                    chat_id=chat_id,
                    messages_template={
                        'alias': 'message_statuses',
                        'kwargs': message_statuses
                    },
                    editable_message_id=exist_status_message[0]
                )
                database.keep_message(
                    message_id=editable_message.message_id,
                    chat_id=editable_message.chat.id,
                    message_type='status_message',
                    message_content=message_statuses
                )
                log.info('[Bot]: Message with type `status_message` for user %s has been updated', user_id)
            elif not diff_between_messages:
                log.info('[Bot]: Message with type `status_message` for user %s is actual, skip', user_id)
        else:
            status_message = telegram.send_styled_message(
                chat_id=chat_id,
                messages_template={
                    'alias': 'message_statuses',
                    'kwargs': message_statuses
                }
            )
            bot.pin_chat_message(
                chat_id=status_message.chat.id,
                message_id=status_message.id
            )
            database.keep_message(
                message_id=status_message.message_id,
                chat_id=status_message.chat.id,
                message_type='status_message',
                message_content=message_statuses
            )
            log.info('[Bot]: Message with type `status_message` for user %s has been created', user_id)
    except TypeError as exception:
        exception_context = {
            'message': f"Failed to update the message with the status of received messages for user {user_id}",
            'exception': exception,
            'exist_status_message': exist_status_message,
            'message_statuses': message_statuses,
            'diff_between_messages': diff_between_messages
        }
        log.error(exception_context)


def get_message_statuses(
    user_id: str = None
) -> dict:
    """
    Returns the queue and processed posts for the user.

    Args:
        user_id (str): The user id.

    Returns:
        dict: The queue and processed posts for the user.

    Examples:
        >>> get_message_statuses(user_id='1234567890')
        {'queue': '<code>queue is empty</code>', 'processed': '<code>no processed posts</code>'}
    """
    queue_dict = database.get_user_queue(user_id=user_id)
    processed_dict = database.get_user_processed(user_id=user_id)

    queue_string = ''
    if queue_dict is not None:
        sorted_data = sorted(queue_dict[user_id], key=lambda x: x['scheduled_time'], reverse=False)
        for item in sorted_data:
            queue_string = queue_string + f"+ <code>{item['post_id']}: will be started {item['scheduled_time']}</code>\n"
    else:
        queue_string = '<code>queue is empty</code>'

    processed_string = ''
    if processed_dict is not None:
        sorted_data = sorted(processed_dict[user_id], key=lambda x: x['timestamp'], reverse=False)
        for item in sorted_data:
            processed_string = processed_string + f"* <code>{item['post_id']}: {item['state']} at {item['timestamp']}</code>\n"
    else:
        processed_string = '<code>no processed posts</code>'

    return {'queue': queue_string, 'processed': processed_string}


def post_link_message_parser(message: telegram.telegram_types.Message = None) -> dict:
    """
    Parses the message containing the Instagram post link and returns the data.

    Args:
        message (telegram.telegram_types.Message): The message object containing the post link.

    Returns:
        dict: The data containing the user id, post url, post id, post owner, link type, message id, and chat id.

    Raises:
        InvalidPostId: The post id is invalid.
        InvalidPostLink: The post link is invalid.
    """
    data = {}
    if re.match(r'^https://www.instagram.com/(p|reel)/.*', message.text):
        post_id = message.text.split('/')[4]
        if len(post_id) == 11 and re.match(r'^[a-zA-Z0-9_]+$', post_id):
            data['user_id'] = message.chat.id
            data['post_url'] = message.text
            data['post_id'] = post_id
            data['post_owner'] = 'undefined'
            data['link_type'] = 'post'
            data['message_id'] = message.id
            data['chat_id'] = message.chat.id
        else:
            log.error('[Bot]: Post id %s from user %s is wrong', post_id, message.chat.id)
            telegram.send_styled_message(
                chat_id=message.chat.id,
                messages_template={'alias': 'url_error'}
            )
    else:
        log.error('[Bot]: Post link %s from user %s is incorrect', message.text, message.chat.id)
        telegram.send_styled_message(
            chat_id=message.chat.id,
            messages_template={'alias': 'url_error'}
        )
    return data
# END BLOCK ADDITIONAL FUNCTIONS ######################################################################################################


# START BLOCK PROCESSING FUNCTIONS ####################################################################################################
def process_one_post(
    message: telegram.telegram_types.Message = None,
    help_message: telegram.telegram_types.Message = None,
    mode: str = 'single'
) -> None:
    """
    Processes an Instagram post link sent by a user and adds it to the queue for download.

    Args:
        message (telegram.telegram_types.Message): The Telegram message object containing the post link.
        help_message (telegram.telegram_types.Message): The help message to be deleted.
        mode (str, optional): The mode of processing. Defaults to 'single'.

    Returns:
        None
    """
    # Check permissions
    user = users_rl.user_access_check(message.chat.id, ROLES_MAP['Post'])
    if user.get('permissions', None) == users_rl.user_status_allow:
        data = post_link_message_parser(message)
        time_to_process = user.get('rate_limits', {}).get('end_time', None)

        if data:
            if time_to_process is None:
                data['scheduled_time'] = datetime.now()
            else:
                data['scheduled_time'] = time_to_process

            if database.check_message_uniqueness(data['post_id'], data['user_id']):
                _ = database.add_message_to_queue(data)
                update_status_message(user_id=message.chat.id)
                log.info('[Bot]: Post link %s for user %s added in queue', message.text, message.chat.id)
            else:
                log.info('[Bot]: Post %s for user %s already in queue or processed', data['post_id'], message.chat.id)

            if mode == 'single':
                telegram.delete_message(message.chat.id, message.id)
                if help_message is not None:
                    telegram.delete_message(message.chat.id, help_message.id)
    else:
        telegram.send_styled_message(
            chat_id=message.chat.id,
            messages_template={
                'alias': 'reject_message',
                'kwargs': {'username': message.chat.username, 'userid': message.chat.id}
            }
        )


def process_list_posts(
    message: telegram.telegram_types.Message = None,
    help_message: telegram.telegram_types.Message = None
) -> None:
    """
    Process a list of Instagram post links.

    Args:
        message (telegram.telegram_types.Message, optional): The message containing the list of post links. Defaults to None.
        help_message (telegram.telegram_types.Message, optional): The help message to be deleted. Defaults to None.

    Returns:
        None
    """
    user = users.user_access_check(message.chat.id, ROLES_MAP['Posts List'])
    if user.get('permissions', None) == users.user_status_allow:
        for link in message.text.split('\n'):
            message.text = link
            process_one_post(
                message=message,
                help_message=help_message,
                mode='list'
            )
        telegram.delete_message(message.chat.id, message.id)
        if help_message is not None:
            telegram.delete_message(message.chat.id, help_message.id)
    else:
        telegram.send_styled_message(
            chat_id=message.chat.id,
            messages_template={
                'alias': 'reject_message',
                'kwargs': {'username': message.chat.username, 'userid': message.chat.id}
            }
        )
# END BLOCK PROCESSING FUNCTIONS ####################################################################################################


# SPECIFIED THREADS ###############################################################################################################
def status_message_updater_thread() -> None:
    """
    The handler for the status message.

    Args:
        None

    Returns:
        None
    """
    log.info('[Message-updater-thread]: Starting thread for status message updater...')
    while True:
        try:
            time.sleep(STATUSES_MESSAGE_FREQUENCY)
            if database.users_list():
                for user in database.users_list():
                    user_id = user[0]
                    update_status_message(user_id=user_id)
        # pylint: disable=broad-exception-caught
        except Exception as exception:
            exception_context = {
                'call': threading.current_thread().name,
                'message': 'Failed to update the message with the status of received messages ',
                'users_list': database.users_list(),
                'user': user,
                'exception': exception
            }
            raise FailedMessagesStatusUpdater(exception_context) from exception


def queue_handler_thread() -> None:
    """
    The handler for the queue of posts to be processed.

    Args:
        None

    Returns:
        None
    """
    log.info('[Queue-handler-thread]: Starting thread for queue handler...')
    while True:
        time.sleep(QUEUE_FREQUENCY)
        message = database.get_message_from_queue(datetime.now())

        if message is not None:
            link_type = message[5]
            download_status = message[9]
            upload_status = message[10]
            post_id = message[2]
            owner_id = message[4]
            short_code = message[1]

            if link_type == 'post':
                log.info('[Queue-handler-thread] Starting handler for post url %s...', message[3])
                # download the contents of an instagram post to a temporary folder
                if download_status != 'completed':
                    download_metadata = downloader.get_post_content(shortcode=short_code)
                    database.update_message_state_in_queue(
                        post_id=post_id,
                        state='processing',
                        download_status=download_metadata['status'],
                        upload_status=upload_status
                    )
                # upload the received content to the destination storage
                if upload_status != 'completed':
                    upload_status = uploader.run_transfers(sub_directory=owner_id)
                    database.update_message_state_in_queue(
                        post_id=post_id,
                        state='processing',
                        download_status=download_status,
                        upload_status=upload_status
                    )
                # mark item in queue as processed
                if download_status == 'completed' and upload_status == 'completed':
                    database.update_message_state_in_queue(
                        post_id=post_id,
                        state='processed',
                        download_status=download_status,
                        upload_status=upload_status
                    )
                    log.info('[Queue-handler-thread] The URL of the post %s has been processed', post_id)
                else:
                    log.warning('[Queue-handler-thread] The URL of the post %s has not been processed:\n%s', post_id, message)
        else:
            log.info("[Queue-handler-thread] no messages in the queue for processing")
# SPECIFIED THREADS ###############################################################################################################


def main():
    """
    The main entry point of the project.

    Args:
        None

    Returns:
        None
    """
    # Thread for processing queue
    thread_queue_handler_thread = threading.Thread(target=queue_handler_thread, args=(), name="Thread-queue-handler")
    thread_queue_handler_thread.start()
    # Thread for update status message
    thread_status_message = threading.Thread(target=status_message_updater_thread, args=(), name="Thread-message-updater")
    thread_status_message.start()
    # Run bot
    telegram.launch_bot()


if __name__ == "__main__":
    main()
