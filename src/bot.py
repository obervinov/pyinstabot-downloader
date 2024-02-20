"""
This module contains the main code for the bot
to work and contains the main logic linking the additional modules.
"""
import re
import threading
import time
from datetime import datetime
from logger import log
from telegram import TelegramBot
from users import Users
from messages import Messages
from vault import VaultClient
# from modules.downloader import Downloader
# from modules.uploader import Uploader
from modules.database import DatabaseClient
from configs import constants


# init instances
vault = VaultClient(name=constants.TELEGRAM_BOT_NAME)
telegram = TelegramBot(vault=vault)
bot = telegram.telegram_bot
# Users module with rate limits option
users_rl = Users(vault=vault)
# Users module without rate limits option
users = Users(vault=vault, rate_limits=False)
messages = Messages()
# downloader = Downloader(
#    auth={
#        'sessionfile': constants.INSTAGRAM_SESSION
#    },
#    settings={
#        'savepath': constants.TEMPORARY_DIR,
#        'useragent': constants.INSTAGRAM_USERAGENT
#    },
#    vault=vault
# )
# uploader = Uploader(
#    storage={
#        'type': constants.STORAGE_TYPE,
#        'temporary': constants.TEMPORARY_DIR,
#        'cloud_root_path': constants.BOT_NAME,
#        'exclude_type': constants.STORAGE_EXCLUDE_TYPE
#    },
#    vault=vault
# )
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
        log.info(
            '[Bot]: Processing `start` command for user %s...',
            message.chat.id
        )
        reply_markup = telegram.create_inline_markup(constants.ROLES_MAP.keys())
        start_message = telegram.send_styled_message(
            chat_id=message.chat.id,
            messages_template={
                'alias': 'start_message',
                'kwargs': {
                    'username': message.from_user.username,
                    'userid': message.chat.id
                }
            },
            reply_markup=reply_markup
        )
        bot.pin_chat_message(start_message.chat.id, start_message.id)
    else:
        telegram.send_styled_message(
            chat_id=message.chat.id,
            messages_template={
                'alias': 'reject_message',
                'kwargs': {
                    'username': message.chat.username,
                    'userid': message.chat.id
                }
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
    log.info(
        '[Bot]: Processing button %s for user %s...',
        call.data,
        call.message.chat.id
    )
    if users.user_access_check(call.message.chat.id, constants.ROLES_MAP[call.data]).get('permissions', None) == users.user_status_allow:
        if call.data == "Post":
            button_post(
                call=call
            )
        elif call.data == "Posts List":
            button_posts_list(
                call=call
            )
        elif call.data == "User Queue":
            button_user_queue(
                call=call
            )
        elif call.data == "Profile Posts":
            button_profile_posts(
                call=call
            )
        else:
            log.error(
                '[Bot]: Handler for button %s not found',
                call.data
            )
    else:
        telegram.send_styled_message(
            chat_id=call.message.chat.id,
            messages_template={
                'alias': 'permission_denied_message',
                'kwargs': {
                    'username': call.message.chat.username,
                    'userid': call.message.chat.id
                }
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
        log.error(
            '[Bot]: Invalid command `%s` from user %s',
            message.text,
            message.chat.id
        )
        telegram.send_styled_message(
            chat_id=message.chat.id,
            messages_template={'alias': 'unknown_command'}
        )
    else:
        telegram.send_styled_message(
            chat_id=message.chat.id,
            messages_template={
                'alias': 'reject_message',
                'kwargs': {
                    'username': message.chat.username,
                    'userid': message.chat.id
                }
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
    user = users.user_access_check(call.message.chat.id, constants.ROLES_MAP['Post'])
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
                'kwargs': {
                    'username': call.message.chat.username,
                    'userid': call.message.chat.id
                }
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
    user = users.user_access_check(call.message.chat.id, constants.ROLES_MAP['Posts List'])
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
                'kwargs': {
                    'username': call.message.chat.username,
                    'userid': call.message.chat.id
                }
            }
        )


# Inline button handler for Profile Posts
def button_user_queue(call: telegram.callback_query = None) -> None:
    """
    The handler for the Profile Posts button.

    Args:
        call (telegram.callback_query): The callback query object.

    Returns:
        None
    """
    if users.user_access_check(call.message.chat.id, constants.ROLES_MAP['User Queue']).get('permissions', None) == users.user_status_allow:
        queue_dict = database.get_user_queue(call.message.chat.id)
        queue_string = ''
        if queue_dict is not None:
            for item in queue_dict[call.message.chat.id]:
                queue_string = queue_string + f"+ <code>{item['post_id']}: {item['scheduled_time']}</code>\n"
        else:
            queue_string = '<code>empty</code>'
        telegram.send_styled_message(
            chat_id=call.message.chat.id,
            messages_template={
                'alias': 'user_queue',
                'kwargs': {
                    'userid': call.message.chat.id,
                    'queue': queue_string
                }
            }
        )
    else:
        telegram.send_styled_message(
            chat_id=call.message.chat.id,
            messages_template={
                'alias': 'permission_denied_message',
                'kwargs': {
                    'username': call.message.chat.username,
                    'userid': call.message.chat.id
                }
            }
        )


# Inline button handler for Profile Posts
def button_profile_posts(call: telegram.callback_query = None) -> None:
    """
    The handler for the Profile Posts button.

    Args:
        call (telegram.callback_query): The callback query object.

    Returns:
        None
    """
    if users.user_access_check(call.message.chat.id, constants.ROLES_MAP['Profile Posts']).get('permissions', None) == users.user_status_allow:
        telegram.send_styled_message(
            chat_id=call.message.chat.id,
            messages_template={'alias': 'feature_not_implemented'}
        )
    else:
        telegram.send_styled_message(
            chat_id=call.message.chat.id,
            messages_template={
                'alias': 'permission_denied_message',
                'kwargs': {
                    'username': call.message.chat.username,
                    'userid': call.message.chat.id
                }
            }
        )


# START BLOCK ADDITIONAL FUNCTIONS ######################################################################################################
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
            log.error(
                '[Bot]: Post id %s from user %s is wrong',
                post_id,
                message.chat.id
            )
            telegram.send_styled_message(
                chat_id=message.chat.id,
                messages_template={'alias': 'url_error'}
            )
    else:
        log.error(
            '[Bot]: Post link %s from user %s is incorrect',
            message.text,
            message.chat.id
        )
        telegram.send_styled_message(
            chat_id=message.chat.id,
            messages_template={'alias': 'url_error'}
        )
    return data
# END BLOCK ADDITIONAL FUNCTIONS ######################################################################################################


# START BLOCK PROCESSING FUNCTIONS ####################################################################################################
def process_one_post(
    message: telegram.telegram_types.Message = None,
    help_message: telegram.telegram_types.Message = None
) -> None:
    """
    Processes an Instagram post link sent by a user and adds it to the queue for download.

    Args:
        message (telegram.telegram_types.Message): The Telegram message object containing the post link.
        help_message (telegram.telegram_types.Message): The help message to be deleted.
        time_to_process (datetime): The scheduled time to process the post link.

    Returns:
        None
    """
    # Check permissions
    user = users_rl.user_access_check(message.chat.id, constants.ROLES_MAP['Post'])
    if user.get('permissions', None) == users_rl.user_status_allow:
        data = post_link_message_parser(message)
        time_to_process = user.get('requests_ratelimits', {}).get('end_time', None)
        if data:
            if time_to_process is None:
                data['scheduled_time'] = datetime.now()
            else:
                data['scheduled_time'] = time_to_process

            if database.check_message_uniqueness(data['post_id'], data['user_id']):
                response_message = telegram.send_styled_message(
                    chat_id=message.chat.id,
                    messages_template={'alias': 'added_in_queue'}
                )
                bot.delete_message(message.chat.id, message.id)
                if help_message is not None:
                    bot.delete_message(message.chat.id, help_message.id)
                data['response_message_id'] = response_message.id
                _ = database.add_message_to_queue(data)
                log.info(
                    '[Bot]: Post link %s for user %s added in queue',
                    message.text,
                    message.chat.id
                )
            else:
                log.info(
                    '[Bot]: Post %s for user %s already in queue or processed',
                    data['post_id'],
                    message.chat.id
                )
                telegram.send_styled_message(
                    chat_id=message.chat.id,
                    messages_template={
                        'alias': 'post_already_downloaded',
                        'kwargs': {'post_id': data['post_id']}
                    }
                )
    else:
        telegram.send_styled_message(
            chat_id=message.chat.id,
            messages_template={
                'alias': 'reject_message',
                'kwargs': {
                    'username': message.chat.username,
                    'userid': message.chat.id
                }
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
    user = users.user_access_check(message.chat.id, constants.ROLES_MAP['Posts List'])
    if user.get('permissions', None) == users.user_status_allow:
        pattern = re.compile(r'^https://www.instagram.com/(p|reel)/.*(\n^https://www.instagram.com/(p|reel)/.*)*$')
        if bool(pattern.match(message.text)):
            links = message.text.split('\n')
            for link in links:
                # To register each link as a separate request for account rate limits
                user = users_rl.user_access_check(message.chat.id, constants.ROLES_MAP['Posts List'])
                message.text = link
                if user.get('rate_limits', None).get('end_time', None) is None:
                    time_to_process = datetime.now()
                else:
                    time_to_process = user['rate_limits']['end_time']
                process_one_post(
                    message=message,
                    help_message=help_message,
                    time_to_process=time_to_process
                )
                bot.delete_message(message.chat.id, message.id)
                if help_message is not None:
                    bot.delete_message(message.chat.id, help_message.id)
        else:
            telegram.send_styled_message(
                chat_id=message.chat.id,
                messages_template={'alias': 'url_error'}
            )
            log.error(
                '[Bot]: List of post links from user %s is incorrect: %s',
                message.chat.id,
                message.text
            )
    else:
        telegram.send_styled_message(
            chat_id=message.chat.id,
            messages_template={
                'alias': 'reject_message',
                'kwargs': {
                    'username': message.chat.username,
                    'userid': message.chat.id
                }
            }
        )
# END BLOCK PROCESSING FUNCTIONS ####################################################################################################


def queue_handler() -> None:
    """
    The handler for the queue of posts to be processed.

    Args:
        None

    Returns:
        None
    """
    log.info(
        '[Bot]: Starting thread for queue handler...'
    )
    while True:
        time.sleep(constants.QUEUE_FREQUENCY)
        message = database.get_message_from_queue(datetime.now())

        if message is not None:
            link_type = message[5]
            download_status = message[9]
            upload_status = message[10]
            post_id = message[2]
            chat_id = message[1]
            message_id = message[7]

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
                    # send a message to the user with a link to the uploaded file
                    bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=messages.render_template(
                            template_alias='post_downloaded',
                            post_id=post_id,
                            timestamp=str(datetime.now())
                        )
                    )
                    log.info(
                        '[Queue-thread-1] The URL of the post %s has been processed',
                        post_id
                    )


def main():
    """
    The main entry point of the project.

    Args:
        None

    Returns:
        None
    """
    # Thread for processing queue
    thread_queue_handler = threading.Thread(
        target=queue_handler,
        args=()
    )
    thread_queue_handler.start()
    telegram.launch_bot()


if __name__ == "__main__":
    main()
