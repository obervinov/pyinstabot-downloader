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
from telegram import exceptions as TelegramExceptions
from users import Users
from vault import VaultClient
from configs.constants import (TELEGRAM_BOT_NAME, ROLES_MAP, QUEUE_FREQUENCY, STATUSES_MESSAGE_FREQUENCY)
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
downloader_api_enabled = vault.read_secret(path='configuration/downloader-api').get('enabled', False)
if downloader_api_enabled == 'True':
    log.info('[Bot]: downloader API is enabled: %s', downloader_api_enabled)
    downloader = Downloader(vault=vault)
else:
    log.warning('[Bot]: downloader API is disabled, using mock object, because enabled flag is %s', downloader_api_enabled)
    downloader = MagicMock()
    downloader.get_post_content.return_value = {
        'post': f"mock_{''.join(random.choices(string.ascii_letters + string.digits, k=10))}",
        'owner': 'undefined',
        'type': 'fake',
        'status': 'completed'
    }

# Client for upload content to the cloud storage
# If API disabled, the mock object will be used
uploader_api_enabled = vault.read_secret(path='configuration/uploader-api').get('enabled', False)
if uploader_api_enabled == 'True':
    log.info('[Bot]: uploader API is enabled: %s', uploader_api_enabled)
    uploader = Uploader(vault=vault)
else:
    log.warning('[Bot]: uploader API is disabled, using mock object, because enabled flag is %s', uploader_api_enabled)
    uploader = MagicMock()
    uploader.run_transfers.return_value = 'completed'

# Client for communication with the database
database = DatabaseClient(vault=vault)


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
    log.info('[Bot]: Processing button `%s` for user %s...', call.data, call.message.chat.id)
    if users.user_access_check(call.message.chat.id, ROLES_MAP[call.data]).get('permissions', None) == users.user_status_allow:
        if call.data == "Post":
            button_post(call=call)
        elif call.data == "Posts List":
            button_posts_list(call=call)
        elif call.data == "Reschedule Queue":
            button_reschedule_queue(call=call)
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


# Inline button handler for Reschedule Queue
def button_reschedule_queue(call: telegram.callback_query = None) -> None:
    """
    The handler for the Reschedule Queue button.

    Args:
        call (telegram.callback_query): The callback query object.

    Returns:
        None
    """
    user = users.user_access_check(call.message.chat.id, ROLES_MAP['Reschedule Queue'])
    if user.get('permissions', None) == users.user_status_allow:
        help_message = telegram.send_styled_message(
            chat_id=call.message.chat.id,
            messages_template={'alias': 'help_for_reschedule_queue'}
        )
        bot.register_next_step_handler(
            call.message,
            reschedule_queue,
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
def update_status_message(user_id: str = None) -> None:
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
        message_statuses = get_user_messages(user_id=user_id)
        diff_between_messages = False
        if exist_status_message:
            # check difference between messages content
            if exist_status_message[4] != get_hash(message_statuses):
                diff_between_messages = True

            # if message already sended and expiring (because bot can edit message only first 48 hours)
            # automatic renew message every 23 hours
            if exist_status_message[2] < datetime.now() - timedelta(hours=24):
                if exist_status_message[2] < datetime.now() - timedelta(hours=48):
                    log.warning('[Bot]: `status_message` for user %s old more than 48 hours, can not delete them', user_id)
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
                log.info('[Bot]: `status_message` for user %s has been renewed', user_id)
            elif message_statuses is not None and diff_between_messages:
                log.info(
                    '[Bot]: `status_message` for user %s is outdated, updating %s -> %s...',
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
                log.info('[Bot]: `status_message` for user %s has been updated', user_id)
            elif not diff_between_messages:
                log.info('[Bot]: `status_message` for user %s is actual', user_id)
        else:
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
            log.info('[Bot]: `status_message` for user %s has been created', user_id)
    except TypeError as exception:
        exception_context = {
            'message': f"Failed to update the message with the status of received messages for user {user_id}",
            'exception': exception,
            'exist_status_message': exist_status_message,
            'message_statuses': message_statuses,
            'diff_between_messages': diff_between_messages
        }
        log.error(exception_context)


def get_user_messages(user_id: str = None) -> dict:
    """
    Returns the queue and processed posts for the user.

    Args:
        user_id (str): The user id.

    Returns:
        dict: The queue and processed posts for the user.

    Examples:
        >>> get_user_messages(user_id='1234567890')
        {'queue': '<code>queue is empty</code>', 'processed': '<code>processed is empty</code>'}
    """
    queue_dict = database.get_user_queue(user_id=user_id)
    processed_dict = database.get_user_processed(user_id=user_id)

    queue_string = ''
    if queue_dict is not None:
        sorted_data = sorted(queue_dict[user_id], key=lambda x: x['scheduled_time'], reverse=False)
        for item in sorted_data:
            queue_string = queue_string + f"+ <code>{item['post_id']}: scheduled for {item['scheduled_time']}</code>\n"
    else:
        queue_string = '<code>queue is empty</code>'

    processed_string = ''
    if processed_dict is not None:
        sorted_data = sorted(processed_dict[user_id], key=lambda x: x['timestamp'], reverse=False)
        for item in sorted_data:
            processed_string = processed_string + f"* <code>{item['post_id']}: {item['state']} at {item['timestamp']}</code>\n"
    else:
        processed_string = '<code>processed is empty</code>'

    return {'queue': queue_string, 'processed': processed_string}


def message_parser(message: telegram.telegram_types.Message = None) -> dict:
    """
    Parses the message containing the Instagram post link and returns the data.

    Args:
        message (telegram.telegram_types.Message): The message object containing the post link.

    Returns:
        dict: The data containing the user id, post url, post id, post owner, link type, message id, and chat id.
    """
    data = {}
    if re.match(r'^https://www.instagram.com/(p|reel)/.*', message.text):
        post_id = message.text.split('/')[4]
        if len(post_id) == 11 and re.match(r'^[a-zA-Z0-9_-]+$', post_id):
            data['user_id'] = message.chat.id
            data['post_url'] = message.text
            data['post_id'] = post_id
            data['post_owner'] = 'undefined'
            data['link_type'] = 'post'
            data['message_id'] = message.id
            data['chat_id'] = message.chat.id
        else:
            log.error('[Bot]: post id %s from user %s is wrong', post_id, message.chat.id)
            telegram.send_styled_message(
                chat_id=message.chat.id,
                messages_template={'alias': 'url_error'}
            )
    else:
        log.error('[Bot]: post link %s from user %s is incorrect', message.text, message.chat.id)
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
        data = message_parser(message)
        rate_limit = user.get('rate_limits', {}).get('end_time', None)

        # Define time to process the message in queue
        if rate_limit:
            data['scheduled_time'] = rate_limit
        else:
            data['scheduled_time'] = datetime.now()

        # Check if the message is unique
        if database.check_message_uniqueness(data['post_id'], data['user_id']):
            _ = database.add_message_to_queue(data)
            update_status_message(user_id=message.chat.id)
            log.info('[Bot]: post %s from user %s has been added to the queue', message.text, message.chat.id)
        else:
            log.info('[Bot]: post %s from user %s already in queue or processed', data['post_id'], message.chat.id)

        # If it is not a list of posts - delete users message
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


def reschedule_queue(
    message: telegram.telegram_types.Message = None,
    help_message: telegram.telegram_types.Message = None
) -> None:
    """
    Manually reschedules the queue for the user.

    Args:
        message (telegram.telegram_types.Message, optional): The message containing the list of post links. Defaults to None.
        help_message (telegram.telegram_types.Message, optional): The help message to be deleted. Defaults to None.

    Returns:
        None
    """
    user = users.user_access_check(message.chat.id, ROLES_MAP['Reschedule Queue'])
    if user.get('permissions', None) == users.user_status_allow:
        for item in message.text.split('\n'):
            item = item.split('-')
            post_id = item[0].strip()
            new_scheduled_time = datetime.strptime(item[1].strip(), '%Y-%m-%d %H:%M:%S')
            if (
                isinstance(post_id, str) and len(post_id) == 11 and
                isinstance(new_scheduled_time, datetime) and new_scheduled_time > datetime.now()
            ):
                database.update_schedule_time_in_queue(
                    post_id=post_id,
                    user_id=message.chat.id,
                    scheduled_time=new_scheduled_time
                )
            else:
                telegram.send_styled_message(
                    chat_id=message.chat.id,
                    messages_template={'alias': 'wrong_reschedule_queue'}
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
    Handler thread for monitoring and timely updating of the widget with the status of messages sent by the user.

    Args:
        None

    Returns:
        None
    """
    log.info('[Message-updater-thread]: started thread for `status_message` updater')
    while True:
        try:
            time.sleep(STATUSES_MESSAGE_FREQUENCY)
            if database.get_users():
                for user in database.get_users():
                    user_id = user[0]
                    update_status_message(user_id=user_id)
        # pylint: disable=broad-exception-caught
        except Exception as exception:
            exception_context = {
                'call': threading.current_thread().name,
                'message': 'Failed to update the message with the status of received messages ',
                'users': database.get_users(),
                'user': user,
                'exception': exception
            }
            raise FailedMessagesStatusUpdater(exception_context) from exception


def queue_handler_thread() -> None:
    """
    Handler thread to process messages from the queue at the specified time.

    Args:
        None

    Returns:
        None
    """
    log.info('[Queue-handler-thread]: started thread for queue handler')

    while True:
        time.sleep(QUEUE_FREQUENCY)
        message = database.get_message_from_queue(datetime.now())

        if message is not None:
            download_status = message[9]
            upload_status = message[10]
            post_id = message[2]
            owner_id = message[4]

            log.info('[Queue-handler-thread] starting handler for post url %s...', message[3])
            # download the contents of an instagram post to a temporary folder
            if download_status not in ['completed', 'not_found']:
                download_metadata = downloader.get_post_content(shortcode=post_id)
                owner_id = download_metadata['owner']
                download_status = download_metadata['status']
                database.update_message_state_in_queue(
                    post_id=post_id,
                    state='processing',
                    download_status=download_status,
                    upload_status=upload_status,
                    post_owner=owner_id
                )
            # downloader couldn't find the post for some reason
            if download_status == 'not_found':
                database.update_message_state_in_queue(
                    post_id=post_id,
                    state='processed',
                    download_status=download_status,
                    upload_status=download_status,
                    post_owner=owner_id
                )
            # upload the received content to the destination storage
            if upload_status != 'completed' and download_status == 'completed':
                upload_status = uploader.run_transfers(sub_directory=owner_id)
                database.update_message_state_in_queue(
                    post_id=post_id,
                    state='processing',
                    download_status=download_status,
                    upload_status=upload_status,
                    post_owner=owner_id
                )
            # mark item in queue as processed
            if download_status == 'completed' and upload_status == 'completed':
                database.update_message_state_in_queue(
                    post_id=post_id,
                    state='processed',
                    download_status=download_status,
                    upload_status=upload_status,
                    post_owner=owner_id
                )
                log.info('[Queue-handler-thread] the post %s has been processed successfully', post_id)
            elif download_status == 'not_found' and upload_status == 'not_found':
                log.warning('[Queue-handler-thread] the post %s not found, message was marked as processed', post_id)
            else:
                log.warning(
                    '[Queue-handler-thread] the post %s has not been processed yet (download: %s, uploader: %s)',
                    post_id, download_status, upload_status
                )
        else:
            log.info("[Queue-handler-thread] no messages in the queue for processing at the moment, waiting...")
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
    while True:
        try:
            telegram.launch_bot()
        except TelegramExceptions.FailedToCreateInstance as telegram_api_exception:
            log.error('[Bot]: main thread failed, restart thread: %s', telegram_api_exception)
            time.sleep(5)


if __name__ == "__main__":
    main()
