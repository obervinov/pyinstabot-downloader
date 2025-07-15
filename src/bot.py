# pylint: disable=unused-argument
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
tg = TelegramBot(vault=vault)
# Telegram bot for decorators
bot = tg.telegram_bot
# Client for communication with the database
database = DatabaseClient(vault=vault, db_role=VAULT_DB_ROLE)
# Metrics exporter
metrics = Metrics(port=METRICS_PORT, interval=METRICS_INTERVAL, metrics_prefix=TELEGRAM_BOT_NAME, vault=vault, database=database)
# Users manager instance
users_rl = Users(vault={'instance': vault, 'role': f"{VAULT_DB_ROLE}-users-rl"}, rate_limits=True)
users = Users(vault={'instance': vault, 'role': f"{VAULT_DB_ROLE}-users"}, rate_limits=False)
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


# Bot commands #####################################################################################################################
@bot.message_handler(commands=['start'])
@users.access_control(flow='auth')
def start_command_handler(message: tg.telegram_types.Message, access_result: dict) -> None:
    """
    Processes the main logic of the 'start' command under access control.

    Args:
        message (tg.telegram_types.Message): The message object containing chat information.
        access_result (dict): The dictionary containing the access result. Propagated from the access_control decorator.
    """
    log.info('[Bot]: Processing start command for user %s...', message.chat.id)
    reply_markup = tg.create_inline_markup(ROLES_MAP.keys())
    start_message = tg.send_styled_message(
        chat_id=message.chat.id,
        messages_template={'alias': 'start_message', 'kwargs': {'username': message.from_user.username, 'userid': message.chat.id}},
        reply_markup=reply_markup,
    )
    bot.pin_chat_message(start_message.chat.id, start_message.id)
    bot.delete_message(message.chat.id, message.message_id)
    update_status_message(user_id=message.chat.id)


# Callback query handler for InlineKeyboardButton
@bot.callback_query_handler(func=lambda call: True)
@users.access_control(flow='auth')
def bot_callback_query_handler(call: tg.callback_query, access_result: dict) -> None:
    """
    Processes the button press from the user.

    Args:
        call (tg.callback_query): The callback query§
        access_result (dict): The dictionary containing the access result. Propagated from the access_control decorator.
    """
    log.info('[Bot]: Processing button %s for user %s...', call.data, call.message.chat.id)
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
    help_message = tg.send_styled_message(chat_id=call.message.chat.id, messages_template={'alias': alias})
    bot.register_next_step_handler(call.message, method, help_message)


# Button handlers ###################################################################################################################
@users_rl.access_control(flow='authz', role_id=ROLES_MAP['Posts'])
def post_code_handler(message: tg.telegram_types.Message, data: dict, access_result: dict = None) -> None:
    """
    Processes the post code from the user's message.

    Args:
        message (tg.telegram_types.Message): Required for the access_control decorator.
        data (dict): The dictionary containing the post code.
            user_id (str): The telegram user id.
            post_id (str): The post id (shortcode).
            post_owner (str): The post owner. Defaults to 'undefined'.
            link_type (str): The type of link. Defaults to 'post'.
            message_id (str): The message id in the chat.
            chat_id (str): The chat id in the chat.
        access_result (dict): The dictionary containing the access result. Propagated from the access_control decorator.
    """
    data['scheduled_time'] = access_result.get('rate_limits') or datetime.now()
    if data['link_type'] == 'account':
        # Delay for account parsing
        data['scheduled_time'] += timedelta(minutes=60)
    status = database.add_message_to_queue(data)
    log.info('[Bot]: %s for user_id %s', status, data['user_id'])


@users.access_control(flow='authz', role_id=ROLES_MAP['Posts'])
def process_posts(message: tg.telegram_types.Message, help_message: tg.telegram_types.Message, access_result: dict) -> None:
    """
    Process a single or multiple posts from the user's message.

    Args:
        message (telegram.telegram_types.Message, optional): The message containing the list of post links. Defaults to None.
        help_message (telegram.telegram_types.Message, optional): The help message to be deleted. Defaults to None.
        access_result (dict): The dictionary containing the access result. Propagated from the access_control decorator.
    """
    cleanup_messages = True
    for link in message.text.split('\n'):
        # Verify that the link is a post link
        if re.match(r'^https://www\.instagram\.com/(p|reel)/.*', message.text):
            post_id = link.split('/')[4]
            # Verify that the post id is correct
            if len(post_id) == 11 and re.match(r'^[a-zA-Z0-9_-]+$', post_id):
                if database.check_message_uniqueness(post_id=post_id, user_id=message.chat.id):
                    post_code_handler(message, data={
                            'user_id': message.chat.id, 'post_id': post_id, 'post_owner': 'undefined', 'link_type': 'post',
                            'message_id': message.id, 'chat_id': message.chat.id, 'post_url': link.split('?')[0]
                    })
            else:
                cleanup_messages = False
                log.error('[Bot]: post id %s from user %s is wrong', post_id, message.chat.id)
                tg.send_styled_message(chat_id=message.chat.id, messages_template={'alias': 'url_error', 'kwargs': {'url': message.text}})
        else:
            cleanup_messages = False
            log.error('[Bot]: post link %s from user %s is incorrect', message.text, message.chat.id)
            tg.send_styled_message(chat_id=message.chat.id, messages_template={'alias': 'url_error'})

    if cleanup_messages:
        tg.delete_message(message.chat.id, message.id)
        tg.delete_message(message.chat.id, help_message.id)


@users.access_control(flow='authz', role_id=ROLES_MAP['Account'])
def process_account(message: tg.telegram_types.Message, help_message: tg.telegram_types.Message, access_result: dict) -> None:
    """
    Processes the user's account posts and adds them to the queue for download.

    Args:
        message (telegram.telegram_types.Message): The message object containing the user's account link.
        help_message (telegram.telegram_types.Message, optional): The help message to be deleted.
        access_result (dict): The dictionary containing the access result. Propagated from the access_control decorator.
    """
    if re.match(r'^https://www\.instagram\.com/.*', message.text):
        account_name = message.text.split('/')[3].split('?')[0]
        account_id, cursor = database.get_account_info(username=account_name)
        if not account_id:
            log.info('[Bot]: account %s does not exist in the database, will request data from API', account_name)
            account_info = downloader.get_account_info(username=account_name)
            database.add_account_info(data=account_info)
            account_id = account_info['pk']

        while True:
            posts_list, cursor = downloader.get_account_posts(user_id=account_id, cursor=cursor)
            log.info('[Bot]: received %s posts from account %s', len(posts_list), account_name)
            for post in posts_list:
                if database.check_message_uniqueness(post_id=post.code, user_id=message.chat.id):
                    post_code_handler(message, data={
                            'user_id': message.chat.id, 'post_id': post.code, 'post_owner': account_name, 'link_type': 'account',
                            'message_id': message.id, 'chat_id': message.chat.id,
                            'post_url': f"https://www.instagram.com/{downloader.media_type_links[post.media_type]}/{post.code}"
                    })
            if not cursor:
                log.info('[Bot]: full posts list from account %s retrieved', account_name)
                tg.delete_message(message.chat.id, message.id)
                tg.delete_message(message.chat.id, help_message.id)
                break
            database.add_account_info({'username': account_name, 'cursor': cursor})
            time.sleep(int(downloader.configuration['delay-requests']) * random.randint(5, 50))


@users.access_control(flow='authz', role_id=ROLES_MAP['Reschedule Queue'])
def reschedule_queue(message: tg.telegram_types.Message, help_message: tg.telegram_types.Message, access_result: dict) -> None:
    """
    Manually reschedules the queue for the user.

    Args:
        message (telegram.telegram_types.Message, optional): The message containing the list of post links. Defaults to None.
        help_message (telegram.telegram_types.Message, optional): The help message to be deleted. Defaults to None.
    """
    can_be_deleted = True
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
            tg.send_styled_message(
                chat_id=message.chat.id,
                messages_template={'alias': 'wrong_reschedule_queue', 'kwargs': {'current_time': datetime.now()}}
            )
    if can_be_deleted:
        tg.delete_message(message.chat.id, message.id)
    if help_message is not None:
        tg.delete_message(message.chat.id, help_message.id)


# Internal methods #################################################################################################################
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
                status_message = tg.send_styled_message(
                    chat_id=user_id, messages_template={'alias': 'message_statuses', 'kwargs': message_statuses}
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
                editable_message = tg.send_styled_message(
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
                log.debug('[Bot]: `status_message` for user %s is actual', user_id)
                database.keep_message(
                    message_id=exist_status_message[0],
                    chat_id=exist_status_message[1],
                    message_type='status_message',
                    message_content=message_statuses,
                    state='updated'
                )

        else:
            status_message = tg.send_styled_message(
                chat_id=user_id, messages_template={'alias': 'message_statuses', 'kwargs': message_statuses}
            )
            database.keep_message(
                message_id=status_message.message_id,
                chat_id=status_message.chat.id,
                message_type='status_message',
                message_content=message_statuses,
            )
            log.info('[Bot]: `status_message` for user %s has been created', user_id)
    except TypeError as exception:
        log.error({
            'message': f"Failed to update the message with the status of received messages for user {user_id}",
            'exception': exception, 'exist_status_message': exist_status_message, 'message_statuses': message_statuses,
            'diff_between_messages': diff_between_messages
        })


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
    if queue[:5]:
        for item in queue[:5]:
            queue_string += f"+ <code>{item['post_id']}: scheduled for {item['scheduled_time']}</code>\n"
    else:
        queue_string = '<code>queue is empty</code>'

    processed_string = ''
    if processed[-5:]:
        for item in processed[-5:]:
            processed_string += f"* <code>{item['post_id']}: {item['state']} at {item['timestamp']}</code>\n"
    else:
        processed_string = '<code>processed is empty</code>'

    return {'queue_list': queue_string, 'processed_list': processed_string, 'queue_count': len(queue), 'processed_count': len(processed)}


# Threads ###########################################################################################################################
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


# pylint: disable=too-many-branches, too-many-statements
def queue_handler_thread() -> None:
    """Handler thread to process messages from the queue at the specified time"""
    log.info('[Queue-handler-thread]: started thread for queue handler')

    while True:
        message = database.get_message_from_queue(datetime.now())

        if message is None:
            log.info("[Queue-handler-thread] no messages in the queue for processing at the moment, waiting...")
            time.sleep(QUEUE_FREQUENCY)
            continue

        try:
            (_, _, post_id, _, owner_id, _, _, _, _, download_status, upload_status) = message

        except (IndexError, ValueError) as exception:
            log.error('[Queue-handler-thread] failed to extract data from message: %s\nmessage: %s', exception, message)
            continue

        log.info(
            '[Queue-handler-thread] starting handler for post %s (Current D_Status: %s, U_Status: %s)...',
            post_id, download_status, upload_status
        )

        if download_status not in ['completed', 'source_not_found', 'not_supported']:
            log.info('[Queue-handler-thread] Attempting to download content for post %s', post_id)
            try:
                download_metadata = downloader.get_post_content(shortcode=post_id)
                owner_id = download_metadata.get('owner', owner_id)
                new_download_status = download_metadata.get('status', 'error')
                database.update_message_state_in_queue(
                    post_id=post_id,
                    state='processing',
                    download_status=new_download_status,
                    upload_status=upload_status,
                    post_owner=owner_id
                )
                download_status = new_download_status

            # pylint: disable=broad-exception-caught
            except Exception as error:
                log.error('[Queue-handler-thread] Download failed for post %s: %s', post_id, error)
                download_status = 'download_error'
                database.update_message_state_in_queue(
                    post_id=post_id,
                    state='error',
                    download_status=download_status,
                    upload_status=upload_status,
                    post_owner=owner_id
                )
                continue

        if download_status == 'completed':
            log.info('[Queue-handler-thread] Download completed for post %s. Checking upload status...', post_id)
            if upload_status != 'completed':
                log.info('[Queue-handler-thread] Attempting to upload content for post %s (owner: %s)', post_id, owner_id)
                try:
                    new_upload_status = uploader.run_transfers(sub_directory=owner_id)
                    database.update_message_state_in_queue(
                        post_id=post_id,
                        state='processing',
                        download_status=download_status,
                        upload_status=new_upload_status,
                        post_owner=owner_id
                    )
                    upload_status = new_upload_status
                # pylint: disable=broad-exception-caught
                except Exception as error:
                    log.error('[Queue-handler-thread] Upload failed for post %s: %s', post_id, error)
                    upload_status = 'upload_error'
                    database.update_message_state_in_queue(
                        post_id=post_id,
                        state='error',
                        download_status=download_status,
                        upload_status=upload_status,
                        post_owner=owner_id
                    )
                    continue
            else:
                log.info('[Queue-handler-thread] Upload already completed for post %s. Skipping upload step.', post_id)

        elif download_status == 'source_not_found':
            log.warning('[Queue-handler-thread] Post %s not found. Marking as processed with status "source_not_found".', post_id)
            database.update_message_state_in_queue(
                post_id=post_id,
                state='processed',
                download_status='source_not_found',
                upload_status='source_not_found',
                post_owner=owner_id
            )
            continue

        elif download_status == 'not_supported':
            log.warning('[Queue-handler-thread] Post %s is not supported. Marking as "not_supported".', post_id)
            database.update_message_state_in_queue(
                post_id=post_id,
                state='not_supported',
                download_status='not_supported',
                upload_status='not_supported',
                post_owner=owner_id
            )
            continue

        elif download_status == 'download_error':
            log.error('[Queue-handler-thread] Download error occurred for post %s. Skipping further processing.', post_id)
            continue

        if download_status == 'completed' and upload_status == 'completed':
            database.update_message_state_in_queue(
                post_id=post_id,
                state='processed',
                download_status=download_status,
                upload_status=upload_status,
                post_owner=owner_id
            )
            log.info('[Queue-handler-thread] Post %s has been processed successfully (download: completed, upload: completed).', post_id)
        elif upload_status == 'upload_error':
            log.error('[Queue-handler-thread] Upload error occurred for post %s. Message state remains "error".', post_id)
        else:
            log.warning(
                '[Queue-handler-thread] Post %s has not been fully processed yet (Download: %s, Upload: %s). Will retry.',
                post_id, download_status, upload_status
            )
        time.sleep(QUEUE_FREQUENCY)


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
            tg.launch_bot()
        except TelegramExceptions.FailedToCreateInstance as telegram_api_exception:
            log.error('[Bot]: main thread failed, restart thread: %s', telegram_api_exception)
            time.sleep(5)


if __name__ == "__main__":
    main()
