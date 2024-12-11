"""
This module contains the main code for the bot to work and contains the main logic linking the additional modules.
"""
from datetime import datetime, timedelta
import re
import threading
import time
import random
import string

from mock import MagicMock
from logger import log
from telegram import TelegramBot, exceptions as TelegramExceptions
from users import Users
from vault import VaultClient
from configs.constants import (
    TELEGRAM_BOT_NAME, ROLES_MAP, QUEUE_FREQUENCY, STATUSES_MESSAGE_FREQUENCY, METRICS_PORT, METRICS_INTERVAL, VAULT_DB_ROLE
)
from modules.database import DatabaseClient
from modules.exceptions import FailedMessagesStatusUpdater
from modules.tools import get_hash
from modules.downloader import Downloader
from modules.uploader import Uploader
from modules.metrics import Metrics


# Vault client
vault = VaultClient()
# Telegram instance
telegram = TelegramBot(vault=vault)
# Telegram bot for decorators
bot = telegram.telegram_bot
# Client for communication with the database
database = DatabaseClient(vault=vault, db_role=VAULT_DB_ROLE)
# Metrics exporter
metrics = Metrics(port=METRICS_PORT, interval=METRICS_INTERVAL, metrics_prefix=TELEGRAM_BOT_NAME, vault=vault, database=database)
# Users module with rate limits option
users_rl = Users(vault=vault, rate_limits=True, storage_connection=database.get_connection())
# Users module without rate limits option
users = Users(vault=vault, storage_connection=database.get_connection())

# Client for download content from instagram
# If API disabled, the mock object will be used
downloader_api_enabled = vault.kv2engine.read_secret(path='configuration/downloader-api').get('enabled', False)
if downloader_api_enabled == 'True':
    log.info('[Bot]: Downloader api is enabled: %s', downloader_api_enabled)
    downloader = Downloader(vault=vault)
else:
    log.warning('[Bot]: Downloader api is disabled, using mock object, because enabled flag is %s', downloader_api_enabled)
    downloader = MagicMock()
    downloader.get_post_content.return_value = {
        'post': f"mock_{''.join(random.choices(string.ascii_letters + string.digits, k=10))}", 'owner': 'mock', 'type': 'fake', 'status': 'completed'
    }

# Client for upload content to the target storage
# If API disabled, the mock object will be used
uploader_api_enabled = vault.kv2engine.read_secret(path='configuration/uploader-api').get('enabled', False)
if uploader_api_enabled == 'True':
    log.info('[Bot]: Uploader API is enabled: %s', uploader_api_enabled)
    uploader = Uploader(vault=vault)
else:
    log.warning('[Bot]: Uploader API is disabled, using mock object, because enabled flag is %s', uploader_api_enabled)
    uploader = MagicMock()
    uploader.run_transfers.return_value = 'completed'


# START HANDLERS BLOCK ##############################################################################################################
# Command handler for START command
@bot.message_handler(commands=['start'])
def start_command(message: telegram.telegram_types.Message = None) -> None:
    """
    Sends a startup message to the specified Telegram chat.

    Args:
        message (telegram.telegram_types.Message): The message object containing information about the chat.
    """
    requestor = {'user_id': message.chat.id, 'chat_id': message.chat.id, 'message_id': message.message_id}
    if users.user_access_check(**requestor).get('access', None) == users.user_status_allow:
        log.info('[Bot]: Processing start command for user %s...', message.chat.id)
        # Main pinned message
        reply_markup = telegram.create_inline_markup(ROLES_MAP.keys())
        start_message = telegram.send_styled_message(
            chat_id=message.chat.id,
            messages_template={'alias': 'start_message', 'kwargs': {'username': message.from_user.username, 'userid': message.chat.id}},
            reply_markup=reply_markup
        )
        bot.pin_chat_message(start_message.chat.id, start_message.id)
        bot.delete_message(message.chat.id, message.id)
        update_status_message(user_id=message.chat.id)
    else:
        telegram.send_styled_message(
            chat_id=message.chat.id,
            messages_template={'alias': 'reject_message', 'kwargs': {'username': message.chat.username, 'userid': message.chat.id}}
        )


# Callback query handler for InlineKeyboardButton (BUTTONS)
@bot.callback_query_handler(func=lambda call: True)
def bot_callback_query_handler(call: telegram.callback_query = None) -> None:
    """
    The handler for the callback query from the user.
    Mainly used to handle button presses.

    Args:
        call (telegram.callback_query): The callback query object.
    """
    log.info('[Bot]: Processing button %s for user %s...', call.data, call.message.chat.id)
    requestor = {
        'user_id': call.message.chat.id, 'role_id': ROLES_MAP[call.data],
        'chat_id': call.message.chat.id, 'message_id': call.message.message_id
    }
    if users.user_access_check(**requestor).get('permissions', None) == users.user_status_allow:
        alias = None
        if call.data == "Posts":
            alias = 'help_for_posts_list'
            method = process_posts
        elif call.data == "Account":
            alias = 'help_for_account'
            method = process_account
        elif call.data == "Reschedule Queue":
            alias = 'help_for_reschedule_queue'
            method = reschedule_queue
        else:
            log.error('[Bot]: Handler for button %s not found', call.data)
            alias = 'unknown_command'
            method = None
        help_message = telegram.send_styled_message(chat_id=call.message.chat.id, messages_template={'alias': alias})
        bot.register_next_step_handler(call.message, method, help_message)

    else:
        alias = 'permission_denied_message'
        kwargs = {'username': call.message.chat.username, 'userid': call.message.chat.id}
        telegram.send_styled_message(chat_id=call.message.chat.id, messages_template={'alias': alias, 'kwargs': kwargs})


# Handler for incorrect flow (UNKNOWN INPUT)
@bot.message_handler(regexp=r'.*')
def unknown_command(message: telegram.telegram_types.Message = None) -> None:
    """
    Sends a message to the user if the command is not recognized.

    Args:
        message (telegram.telegram_types.Message): The message object containing the unrecognized command.
    """
    requestor = {'user_id': message.chat.id, 'chat_id': message.chat.id, 'message_id': message.message_id}
    if users.user_access_check(**requestor).get('access', None) == users.user_status_allow:
        log.error('[Bot]: Invalid command %s from user %s', message.text, message.chat.id)
        telegram.send_styled_message(chat_id=message.chat.id, messages_template={'alias': 'unknown_command'})
    else:
        telegram.send_styled_message(
            chat_id=message.chat.id,
            messages_template={'alias': 'reject_message', 'kwargs': {'username': message.chat.username, 'userid': message.chat.id}}
        )
# END HANDLERS BLOCK ##############################################################################################################


# START BLOCK ADDITIONAL FUNCTIONS ######################################################################################################
def update_status_message(user_id: str = None) -> None:
    """
    Updates the status message for the user.

    Args:
        user_id (str): The user id.
    """
    try:
        diff_between_messages = False
        exist_status_message = database.get_considered_message(message_type='status_message', chat_id=user_id)
        message_statuses = get_user_messages(user_id=user_id)

        if exist_status_message:

            # checking competition of status_message update by another thread (concurrency)
            if exist_status_message[5] == 'updating':
                while exist_status_message[5] == 'updating':
                    time.sleep(1)
                    exist_status_message = database.get_considered_message(message_type='status_message', chat_id=user_id)
            else:
                database.keep_message(
                    message_id=exist_status_message[0],
                    chat_id=exist_status_message[1],
                    message_type='status_message',
                    message_content=message_statuses,
                    state='updating'
                )

            diff_between_messages = exist_status_message[4] != get_hash(message_statuses)

            # if message already sended and expiring (because bot can edit message only first 48 hours)
            # automatic renew message every 24 hours
            if exist_status_message[2] < datetime.now() - timedelta(hours=24):
                if exist_status_message[2] > datetime.now() - timedelta(hours=48):
                    _ = bot.delete_message(chat_id=user_id, message_id=exist_status_message[0])
                status_message = telegram.send_styled_message(
                    chat_id=user_id,
                    messages_template={'alias': 'message_statuses', 'kwargs': message_statuses}
                )
                database.keep_message(
                    message_id=status_message.message_id,
                    chat_id=status_message.chat.id,
                    message_type='status_message',
                    message_content=message_statuses,
                    state='updated',
                    recreated=True
                )
                log.info('[Bot]: `status_message` for user %s has been renewed', user_id)

            elif message_statuses is not None and diff_between_messages:
                editable_message = telegram.send_styled_message(
                    chat_id=user_id,
                    messages_template={'alias': 'message_statuses', 'kwargs': message_statuses},
                    editable_message_id=exist_status_message[0]
                )
                database.keep_message(
                    message_id=editable_message.message_id,
                    chat_id=editable_message.chat.id,
                    message_type='status_message',
                    message_content=message_statuses,
                    state='updated'
                )
                log.info('[Bot]: `status_message` for user %s has been updated', user_id)

            elif not diff_between_messages:
                log.info('[Bot]: `status_message` for user %s is actual', user_id)
                database.keep_message(
                    message_id=exist_status_message[0],
                    chat_id=exist_status_message[1],
                    message_type='status_message',
                    message_content=message_statuses,
                    state='updated'
                )

        else:
            status_message = telegram.send_styled_message(
                chat_id=user_id,
                messages_template={'alias': 'message_statuses', 'kwargs': message_statuses}
            )
            database.keep_message(
                message_id=status_message.message_id,
                chat_id=status_message.chat.id,
                message_type='status_message',
                message_content=message_statuses,
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
        {'queue_list': '<code>queue is empty</code>', 'processed_list': '<code>processed is empty</code>', 'queue_count': 0, 'processed_count': 0}
    """
    queue = database.get_user_queue(user_id=user_id)
    processed = database.get_user_processed(user_id=user_id)

    queue_string = ''
    if queue[:10]:
        for item in queue[:10]:
            queue_string += f"+ <code>{item['post_id']}: scheduled for {item['scheduled_time']}</code>\n"
    else:
        queue_string = '<code>queue is empty</code>'

    processed_string = ''
    if processed[-10:]:
        for item in processed[-10:]:
            processed_string += f"* <code>{item['post_id']}: {item['state']} at {item['timestamp']}</code>\n"
    else:
        processed_string = '<code>processed is empty</code>'

    return {'queue_list': queue_string, 'processed_list': processed_string, 'queue_count': len(queue), 'processed_count': len(processed)}


def message_parser(message: telegram.telegram_types.Message = None) -> dict:
    """
    Parses the message containing the Instagram post link and returns the data.

    Args:
        message (telegram.telegram_types.Message): The message object containing the post link.

    Returns:
        dict: The data containing the user id, post url, post id, post owner, link type, message id, and chat id.
    """
    data = {}
    post_id = None
    post_owner = None
    account_name = None
    if re.match(r'^https://www\.instagram\.com/(p|reel)/.*', message.text):
        post_id = message.text.split('/')[4]
        post_owner = 'undefined'
    elif re.match(r'^https://www\.instagram\.com/.*/(p|reel)/.*', message.text):
        post_id = message.text.split('/')[5]
        post_owner = message.text.split('/')[3]
    elif re.match(r'^https://www\.instagram\.com/.*', message.text):
        account_name = message.text.split('/')[3]
    else:
        log.error('[Bot]: post link %s from user %s is incorrect', message.text, message.chat.id)
        telegram.send_styled_message(chat_id=message.chat.id, messages_template={'alias': 'url_error'})

    if post_id:
        if len(post_id) == 11 and re.match(r'^[теa-zA-Z0-9_-]+$', post_id):
            data['user_id'] = message.chat.id
            data['post_url'] = message.text
            data['post_id'] = post_id
            data['post_owner'] = post_owner
            data['link_type'] = 'post'
            data['message_id'] = message.id
            data['chat_id'] = message.chat.id
        else:
            log.error('[Bot]: post id %s from user %s is wrong', post_id, message.chat.id)
            telegram.send_styled_message(chat_id=message.chat.id, messages_template={'alias': 'url_error', 'kwargs': {'url': message.text}})
    elif account_name:
        data['account_name'] = account_name

    log.info('[Bot]: validation of the link %s from user %s is completed', message.text, message.chat.id)
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

    Notice: This method will merge with the `process_posts` method in v3.3.0.
            After combining the two buttons into a `Posts` button in version 3.2.0, it makes no sense to split one functionality into two methods.

    Args:
        message (telegram.telegram_types.Message): The Telegram message object containing the post link.
        help_message (telegram.telegram_types.Message): The help message to be deleted.
        mode (str, optional): The mode of processing. Defaults to 'single'.
    """
    requestor = {
        'user_id': message.chat.id, 'role_id': ROLES_MAP['Posts'],
        'chat_id': message.chat.id, 'message_id': message.message_id
    }
    user = users_rl.user_access_check(**requestor)
    if user.get('permissions', None) == users_rl.user_status_allow:
        data = message_parser(message)
        if not data:
            log.error('[Bot]: link %s cannot be processed', message.text)
        else:
            rate_limit = user.get('rate_limits', None)

            # Define time to process the message in queue
            if rate_limit:
                data['scheduled_time'] = rate_limit
            else:
                data['scheduled_time'] = datetime.now()

            # Check if the message is unique
            if database.check_message_uniqueness(data['post_id'], data['user_id']):
                status = database.add_message_to_queue(data)
                log.info('[Bot]: %s from user %s', status, message.chat.id)
            else:
                log.info('[Bot]: post %s from user %s already exist in the database', data['post_id'], message.chat.id)

        # If it is not a list of posts - delete users message
        if mode == 'single':
            telegram.delete_message(message.chat.id, message.id)
            if help_message is not None:
                telegram.delete_message(message.chat.id, help_message.id)


def process_posts(
    message: telegram.telegram_types.Message = None,
    help_message: telegram.telegram_types.Message = None
) -> None:
    """
    Process a single or multiple posts from the user's message.

    Args:
        message (telegram.telegram_types.Message, optional): The message containing the list of post links. Defaults to None.
        help_message (telegram.telegram_types.Message, optional): The help message to be deleted. Defaults to None.
    """
    requestor = {
        'user_id': message.chat.id, 'role_id': ROLES_MAP['Posts'],
        'chat_id': message.chat.id, 'message_id': message.message_id
    }
    user = users.user_access_check(**requestor)
    if user.get('permissions', None) == users.user_status_allow:
        for link in message.text.split('\n'):
            message.text = link
            process_one_post(message=message, mode='list')
        telegram.delete_message(message.chat.id, message.id)
        if help_message is not None:
            telegram.delete_message(message.chat.id, help_message.id)


def process_account(
    message: telegram.telegram_types.Message = None,
    help_message: telegram.telegram_types.Message = None
) -> None:
    """
    Processes the user's account posts and adds them to the queue for download.

    Args:
        message (telegram.telegram_types.Message): The message object containing the user's account link. Defaults to None.
        help_message (telegram.telegram_types.Message, optional): The help message to be deleted. Defaults to None.
    """
    requestor = {
        'user_id': message.chat.id, 'role_id': ROLES_MAP['Account'],
        'chat_id': message.chat.id, 'message_id': message.message_id
    }
    user = users.user_access_check(**requestor)
    if user.get('permissions', None) == users.user_status_allow:
        internal_user_id = None
        data = message_parser(message)
        exist_account = database.get_account_info(username=data['account_name'])
        if exist_account:
            log.info('[Bot]: account %s found in the database', data['account_name'])
            internal_user_id = exist_account[2]
        else:
            log.info('[Bot]: account %s does not exist in the database, will request data from Instagram', data['account_name'])
            account_info = downloader.get_account_info(username=data['account_name'])
            database.add_account_info(data=account_info)
            internal_user_id = account_info['pk']
        posts_list = downloader.get_user_posts(user_id=internal_user_id)
        for post in posts_list:
            link = f"https://www.instagram.com/p/{post.code}"
            message.text = link
            process_one_post(message=message, mode='list')

        telegram.delete_message(message.chat.id, message.id)
        if help_message is not None:
            telegram.delete_message(message.chat.id, help_message.id)



def reschedule_queue(
    message: telegram.telegram_types.Message = None,
    help_message: telegram.telegram_types.Message = None
) -> None:
    """
    Manually reschedules the queue for the user.

    Args:
        message (telegram.telegram_types.Message, optional): The message containing the list of post links. Defaults to None.
        help_message (telegram.telegram_types.Message, optional): The help message to be deleted. Defaults to None.
    """
    requestor = {
        'user_id': message.chat.id, 'role_id': ROLES_MAP['Reschedule Queue'],
        'chat_id': message.chat.id, 'message_id': message.message_id
    }
    user = users.user_access_check(**requestor)
    can_be_deleted = True
    if user.get('permissions', None) == users.user_status_allow:
        for item in message.text.split('\n'):
            item = item.split(': scheduled for ')
            post_id = item[0].strip()
            new_scheduled_time = datetime.strptime(item[1].strip(), '%Y-%m-%d %H:%M:%S.%f')
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
                can_be_deleted = False
                telegram.send_styled_message(
                    chat_id=message.chat.id,
                    messages_template={'alias': 'wrong_reschedule_queue', 'kwargs': {'current_time': datetime.now()}}
                )
        if can_be_deleted:
            telegram.delete_message(message.chat.id, message.id)
        if help_message is not None:
            telegram.delete_message(message.chat.id, help_message.id)
# END BLOCK PROCESSING FUNCTIONS ####################################################################################################


# SPECIFIED THREADS ###############################################################################################################
def status_message_updater_thread() -> None:
    """Handler thread for monitoring and timely updating of the widget with the status of messages sent by the user"""
    log.info('[Message-updater-thread]: started thread for "status_message" updater')
    while True:
        time.sleep(STATUSES_MESSAGE_FREQUENCY)
        try:
            users_dict = []
            users_dict = database.get_users()
            for user in users_dict:
                update_status_message(user_id=user['user_id'])
        # pylint: disable=broad-exception-caught
        except Exception as exception:
            exception_context = {
                'call': threading.current_thread().name,
                'message': 'Failed to update the message with the status of received messages',
                'users': users_dict,
                'user': user,
                'exception': exception
            }
            raise FailedMessagesStatusUpdater(exception_context) from exception


def queue_handler_thread() -> None:
    """Handler thread to process messages from the queue at the specified time"""
    log.info('[Queue-handler-thread]: started thread for queue handler')

    while True:
        time.sleep(QUEUE_FREQUENCY)
        message = database.get_message_from_queue(datetime.now())

        if message is not None:
            try:
                download_status = message[9]
                upload_status = message[10]
                post_id = message[2]
                owner_id = message[4]
            except IndexError as exception:
                log.error('[Queue-handler-thread] failed to extract data: %s\nmessage: %s', exception, message)
                break

            log.info('[Queue-handler-thread] starting handler for post %s...', message[2])
            # download the contents of an instagram post to a temporary folder
            if download_status not in ['completed', 'source_not_found', 'not_supported']:
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
            if download_status == 'source_not_found':
                database.update_message_state_in_queue(
                    post_id=post_id,
                    state='processed',
                    download_status=download_status,
                    upload_status=download_status,
                    post_owner=owner_id
                )
            # downloader couldn't download the post for some reason
            if download_status == 'not_supported':
                database.update_message_state_in_queue(
                    post_id=post_id,
                    state='not_supported',
                    download_status='not_supported',
                    upload_status='not_supported',
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
            elif download_status == 'source_not_found' and upload_status == 'source_not_found':
                log.warning('[Queue-handler-thread] the post %s not found, message was marked as processed', post_id)
            elif download_status == 'not_supported' and upload_status == 'not_supported':
                log.errors('[Queue-handler-thread] the post %s is not supported, message was excluded from processing', post_id)
            else:
                log.warning(
                    '[Queue-handler-thread] the post %s has not been processed yet (download: %s, uploader: %s)',
                    post_id, download_status, upload_status
                )
        else:
            log.info("[Queue-handler-thread] no messages in the queue for processing at the moment, waiting...")
# SPECIFIED THREADS ###############################################################################################################


def main():
    """The main entry point of the project"""
    # Thread for processing queue
    thread_queue_handler = threading.Thread(target=queue_handler_thread, args=(), name="QueueHandlerThread")
    thread_queue_handler.start()
    # Thread for update status message
    thread_status_message = threading.Thread(target=status_message_updater_thread, args=(), name="MessageUpdaterThread")
    thread_status_message.start()
    # Thread for export metrics
    threads = threading.enumerate()
    thread_metrics = threading.Thread(target=metrics.run, args=(threads,), name="MetricsThread")
    thread_metrics.start()
    # Run bot
    while True:
        try:
            telegram.launch_bot()
        except TelegramExceptions.FailedToCreateInstance as telegram_api_exception:
            log.error('[Bot]: main thread failed, restart thread: %s', telegram_api_exception)
            time.sleep(5)


if __name__ == "__main__":
    main()
