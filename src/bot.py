"""
This module contains the main code for the bot
to work and contains the main logic linking the additional modules.
"""
import re
import threading
import time
import base64
from datetime import datetime, timedelta
from logger import log
from telegram import TelegramBot
from users import Users
from messages import Messages
from vault import VaultClient
# from modules.downloader import Downloader
# from modules.uploader import Uploader
from modules.database import DatabaseClient
# pylint: disable=unused-import
# flake8: noqa
from configs.constants import (
    PROJECT_ENVIRONMENT, TELEGRAM_BOT_NAME, ROLES_MAP,
    QUEUE_FREQUENCY, STATUSES_MESSAGE_FREQUENCY,
    TEMPORARY_DIR, STORAGE_TYPE, STORAGE_EXCLUDE_TYPE, INSTAGRAM_SESSION, INSTAGRAM_USERAGENT
)


# init instances
vault = VaultClient(name=TELEGRAM_BOT_NAME)
telegram = TelegramBot(vault=vault)
bot = telegram.telegram_bot
# Users module with rate limits option
users_rl = Users(vault=vault)
# Users module without rate limits option
users = Users(vault=vault, rate_limits=False)
messages = Messages()
# downloader = Downloader(
#    auth={'sessionfile': INSTAGRAM_SESSION},
#    settings={'savepath': TEMPORARY_DIR, 'useragent': INSTAGRAM_USERAGENT},
#    vault=vault
# )
# uploader = Uploader(
#    storage={'type': STORAGE_TYPE, 'temporary': TEMPORARY_DIR, 'cloud_root_path': BOT_NAME, 'exclude_type': STORAGE_EXCLUDE_TYPE},
#    vault=vault
# )
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

        # Status message
        exist_status_message = database.get_considered_message(message_type='status_message', chat_id=message.chat.id)
        if database.get_considered_message(message_type='status_message', chat_id=message.chat.id):
            _ = bot.delete_message(
                chat_id=message.chat.id,
                message_id=exist_status_message[0]
            )
        status_message = telegram.send_styled_message(
            chat_id=message.chat.id,
            messages_template={
                'alias': 'statuses_message',
                'kwargs': get_message_statuses(user_id=message.chat.id)
            }
        )
        bot.pin_chat_message(status_message.chat.id, status_message.id)
        # Consider the status message
        database.keep_message(
            message_id=status_message.id,
            chat_id=status_message.chat.id,
            message_type='status_message',
            message_content=get_message_statuses(user_id=message.chat.id)
        )
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
            queue_string = queue_string + f"+ <code>{item['post_id']}: {item['scheduled_time']}</code>\n"
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
        log.debug(user)
        time_to_process = user.get('rate_limits', {}).get('end_time', None)

        if data:
            if time_to_process is None:
                data['scheduled_time'] = datetime.now()
            else:
                data['scheduled_time'] = time_to_process
            log.debug(data['scheduled_time'])
            if database.check_message_uniqueness(data['post_id'], data['user_id']):
                response_message = telegram.send_styled_message(
                    chat_id=message.chat.id,
                    messages_template={'alias': 'added_in_queue'}
                )
                if mode == 'single':
                    bot.delete_message(message.chat.id, message.id)
                    if help_message is not None:
                        bot.delete_message(message.chat.id, help_message.id)
                data['response_message_id'] = response_message.id
                _ = database.add_message_to_queue(data)
                log.info('[Bot]: Post link %s for user %s added in queue', message.text, message.chat.id)
            else:
                log.info('[Bot]: Post %s for user %s already in queue or processed', data['post_id'], message.chat.id)
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
        links = message.text.split('\n')
        for link in links:
            message.text = link
            process_one_post(
                message=message,
                help_message=help_message,
                mode='list'
            )
        bot.delete_message(message.chat.id, message.id)
        if help_message is not None:
            bot.delete_message(message.chat.id, help_message.id)
    else:
        telegram.send_styled_message(
            chat_id=message.chat.id,
            messages_template={
                'alias': 'reject_message',
                'kwargs': {'username': message.chat.username, 'userid': message.chat.id}
            }
        )
# END BLOCK PROCESSING FUNCTIONS ####################################################################################################


def status_message_updater() -> None:
    """
    The handler for the status message.

    Args:
        None

    Returns:
        None
    """
    log.info('[Bot]: Starting thread for status message updater...')
    while True:
        try:
            time.sleep(STATUSES_MESSAGE_FREQUENCY)
            if database.users_list():
                for user in database.users_list():
                    last_status_message = database.get_considered_message(message_type='status_message', chat_id=user[1])
                    statuses_message = get_message_statuses(user_id=user[0])
                    diff_between_messages_content = False

                    # check difference between messages content
                    if last_status_message[3] not in base64.b64encode(str(statuses_message).encode('utf-8')):
                        diff_between_messages_content = True
                    
                    # if message already sended and expiring (because bot can edit message only first 48 hours)
                    # automatic renew message every 23 hours
                    if last_status_message and last_status_message[2] < datetime.now() - timedelta(hours=23):
                        _ = bot.delete_message(
                            chat_id=user[1],
                            message_id=last_status_message[0]
                        )
                        response_message = telegram.send_styled_message(
                            chat_id=user[1],
                            messages_template={
                                'alias': 'statuses_message',
                                'kwargs': statuses_message
                            }
                        )
                        database.keep_message(
                            message_id=response_message.message_id,
                            chat_id=response_message.chat.id,
                            message_type='status_message',
                            message_content=statuses_message
                        )
                        log.info('[Bot]: Message with type `status_message` for user %s has been renewed', user[0])
                    elif statuses_message is not None and diff_between_messages_content:
                        _ = bot.edit_message_text(
                            chat_id=user[1],
                            message_id=last_status_message[0],
                            text=messages.render_template(
                                template_alias='statuses_message',
                                processed=statuses_message['processed'],
                                queue=statuses_message['queue']
                            )
                        )
                        log.info('[Bot]: Message with type `status_message` for user %s has been updated', user[0])
                    elif not diff_between_messages_content:
                        log.info('[Bot]: Message with type `status_message` for user %s is actual, skip', user[0])
                    else:
                        log.warning('[Bot]: Message with type `status_message` for user %s not found', user[0])
        # pylint: disable=broad-exception-caught
        except Exception as exception:
            log.error('[Status-message-updater-thread-1] %s', exception)


def queue_handler() -> None:
    """
    The handler for the queue of posts to be processed.

    Args:
        None

    Returns:
        None
    """
    log.info('[Bot]: Starting thread for queue handler...')
    while True:
        time.sleep(QUEUE_FREQUENCY)
        message = database.get_message_from_queue(datetime.now())

        if message is not None:
            link_type = message[5]
            download_status = message[9]
            upload_status = message[10]
            post_id = message[2]

            if link_type == 'post':
                log.info(
                    '[Queue-thread-1] Starting handler for post url %s...',
                    message[3]
                )
                # download the contents of an instagram post to a temporary folder
                if download_status != 'completed':
                    # download_status = downloader.get_post_content(
                    #    shortcode=message[1]
                    # )
                    download_status = 'completed'
                    database.update_message_state_in_queue(
                        post_id=post_id,
                        state='processing download',
                        download_status=download_status,
                        upload_status=upload_status
                    )
                # upload the received content to the destination storage
                if upload_status != 'completed':
                    # upload_status = uploader.start_upload(
                    #    sub_dir_name=d_response['owner']
                    # )
                    upload_status = 'completed'
                    database.update_message_state_in_queue(
                        post_id=post_id,
                        state='processing upload',
                        download_status=download_status,
                        upload_status=upload_status
                        # upload_status=u_response['status']
                    )
                # mark item in queue as processed
                if download_status == 'completed' and upload_status == 'completed':
                    database.update_message_state_in_queue(
                        post_id=post_id,
                        state='processed',
                        download_status=download_status,
                        upload_status=upload_status
                    )
                    log.info('[Queue-thread-1] The URL of the post %s has been processed', post_id)


def main():
    """
    The main entry point of the project.

    Args:
        None

    Returns:
        None
    """
    # Thread for processing queue
    thread_queue_handler = threading.Thread(target=queue_handler, args=(), name="Thread-queue-handler-1")
    thread_queue_handler.start()
    # Thread for update status message
    thread_status_message = threading.Thread(target=status_message_updater, args=(), name="Thread-status-message-updater-1")
    thread_status_message.start()
    # Run bot
    telegram.launch_bot()


if __name__ == "__main__":
    main()
