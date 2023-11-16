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
from modules.downloader import Downloader
from modules.uploader import Uploader
from modules.database import DatabaseClient
import configs.constants as constants


# instances
vault = VaultClient(name=constants.BOT_NAME)
telegram = TelegramBot(vault=vault)
bot = telegram.telegram_bot
users = Users(vault=vault)
users_without_rl = Users(vault=vault, rate_limits=False)
messages = Messages(config_path=constants.MESSAGES_CONFIG)
#downloader = Downloader(
#    auth={
#        'sessionfile': constants.INSTAGRAM_SESSION
#    },
#    settings={
#        'savepath': constants.TEMPORARY_DIR,
#        'useragent': constants.INSTAGRAM_USERAGENT
#    },
#    vault=vault
#)
#uploader = Uploader(
#    storage={
#        'type': constants.STORAGE_TYPE,
#        'temporary': constants.TEMPORARY_DIR,
#        'cloud_root_path': constants.BOT_NAME,
#        'exclude_type': constants.STORAGE_EXCLUDE_TYPE
#    },
#    vault=vault
#)
database = DatabaseClient(
    vault=vault
)
#
#
# Decorators
#
#
@bot.message_handler(commands=['start'])
def start_command(
    message: telegram.telegram_types.Message = None
) -> None:
    """
    Sends a startup message to the specified Telegram chat.

    Args:
        message (telegram.telegram_types.Message): The message object containing information about the chat.

    Returns:
        None
    """
    # Check user access
    user = users_without_rl.user_access_check(
        user_id=message.chat.id
    )
    if user['access'] == users_without_rl.user_status_allow:
        log.info(
            '[Bot]: Processing start command for user %s...',
            message.chat.id
        )
        reply_markup = telegram.create_inline_markup(
            names=constants.TELEGRAM_STARTUP_BUTTONS,
            size=3
        )
        start_message = send_message(
            chat_id=message.chat.id,
            template={
                'alias': 'start_message',
                'kwargs': {'username': message.from_user.username, 'userid': message.chat.id}
            },
            reply_markup=reply_markup
        )

        bot.pin_chat_message(
            chat_id=start_message.chat.id,
            message_id=start_message.id
        )
    else:
        reject_message(message=message)


# Callback query handler for InlineKeyboardButton
@bot.callback_query_handler(func=lambda call: True)
def bot_callback_query_handler(call):
    log.info(
        '[Bot]: Processing button %s for user %s...',
        call.data,
        call.message.chat.id
    )
    if call.data == "Post":
        # Check permissions
        user = users.user_access_check(
            user_id=call.message.chat.id,
            role_id=constants.POST_ROLE
        )
        if user['access'] == users.user_status_allow and user['permissions'] == users.user_status_allow:
            help_message = send_message(
                chat_id=call.message.chat.id,
                template={'alias': 'help_for_post'}
            )
            bot.register_next_step_handler(
                call.message,
                process_one_post,
                help_message,
                user['rate_limits']['end_time']
            )
        else:
            reject_message(message=call.message)

    elif call.data == "Posts List":
        # Check permissions
        user = users.user_access_check(
            user_id=call.message.chat.id,
            role_id=constants.POSTS_LIST_ROLE
        )
        if user['access'] == users.user_status_allow and user['permissions'] == users.user_status_allow:
            response = send_message(
                chat_id=call.message.chat.id,
                template={'alias': 'help_for_posts_list'}
            )
            bot.register_next_step_handler(
                call.message,
                process_list_posts,
                response
            )
        else:
            reject_message(message=call.message)

    elif call.data == "Profile Posts":
        # Check permissions
        user = users.user_access_check(
            user_id=call.message.chat.id,
            role_id=constants.PROFILE_ROLE
        )
        if user['access'] == users.user_status_allow and user['permissions'] == users.user_status_allow:
            response = send_message(
                chat_id=call.message.chat.id,
                template={'alias': 'help_for_profile_posts'}
            )
            bot.register_next_step_handler(
                call.message,
                process_profile_posts,
                response
            )
        else:
            reject_message(message=call.message)

    elif call.data == "User's Queue":
        # Check permissions
        user = users_without_rl.user_access_check(
            user_id=call.message.chat.id,
            role_id=constants.QUEUE_ROLE
        )
        if user['access'] == users_without_rl.user_status_allow and user['permissions'] == users_without_rl.user_status_allow:
            queue_dict = database.get_user_queue(
                user_id=call.message.chat.id
            )
            queue_string = None
            if queue_dict is not None:
                for item in queue_dict[call.message.chat.id]:
                    queue_string = queue_string + f"+ <code>{item['post_id']}: {item['scheduled_time']}</code>\n"
            else:
                queue_string = '<code>empty</code>'
            send_message(
                chat_id=call.message.chat.id,
                template={
                    'alias': 'user_queue',
                    'kwargs': {'userid': call.message.chat.id, 'queue': queue_string}
                }
            )
        else:
            reject_message(message=call.message)

    else:
        send_message(
            chat_id=call.message.chat.id,
            template={'alias': 'unknown_command'}
        )


def send_message(
    chat_id: str = None,
    template: dict = None,
    reply_markup: telegram.telegram_types.InlineKeyboardMarkup = None
) -> telegram.telegram_types.Message:
    """
    Sends a response message to the user.

    Args:
        chat_id (str): The ID of the chat where the message will be sent.
        template (dict): A dictionary containing the alias of the template to use and any keyword arguments to be passed to the template.
            The dictionary should contain the following keys:
                - alias (str): The alias of the template to use.
                - kwargs (dict): A dictionary containing any keyword arguments to be passed to the template.
        reply_markup (telegram.telegram_types.InlineKeyboardMarkup): The inline keyboard markup to be sent with the message.

    Returns:
        telegram.telegram_types.Message: The message sent to the user.
    """
    return bot.send_message(
        chat_id=chat_id,
        text=messages.render_template(
            template_alias=template['alias'],
            **template.get('kwargs', {})
        ),
        reply_markup=reply_markup,
    )


def reject_message(
    message: telegram.telegram_types.Message = None
) -> None:
    """
    Sends a rejection message to the user who sent the message.

    Args:
        message (telegram.telegram_types.Message): The message object received from the user.

    Returns:
        None
    """
    bot.send_message(
        chat_id=message.chat.id,
        text=messages.render_template(
            template_alias='reject_message',
            username=message.from_user.username,
            userid=message.chat.id
        )
    )


def process_one_post(
    message: telegram.telegram_types.Message = None,
    help_message: telegram.telegram_types.Message = None,
    time_to_process: datetime = None
):
    """
    Processes an Instagram post link sent by a user and adds it to the queue for download.

    Args:
        message (telegram.telegram_types.Message): The Telegram message object containing the post link.
        time_to_process (datetime): The scheduled time to process the post link.

    Returns:
        None
    """
    if re.match(r'^https://www.instagram.com/(p|reel)/.*', message.text):
        data = {}
        data['user_id'] = message.chat.id
        data['post_url'] = message.text
        data['post_id'] = data['post_url'].split('/')[-2]
        data['post_owner'] = 'undefined'
        data['link_type'] = 'post'
        data['message_id'] = message.id
        data['chat_id'] = message.chat.id
        if time_to_process is None:
            data['scheduled_time'] = datetime.now()
        else:
            data['scheduled_time'] = time_to_process

        response_message = send_message(
            chat_id=message.chat.id,
            template={'alias': 'added_in_queue'}
        )
        bot.delete_message(
            chat_id=message.chat.id,
            message_id=message.id
        )
        if help_message is not None:
            bot.delete_message(
                chat_id=message.chat.id,
                message_id=help_message.id
            )
        data['response_message_id'] = response_message.id
        _ = database.add_message_to_queue(
            data=data
        )
        log.info(
            '[Bot]: Post link %s for user %s added in queue',
            message.text,
            message.chat.id
        )
    else:
        send_message(
            chat_id=message.chat.id,
            template={'alias': 'url_error'}
        )
        log.error(
            '[Bot]: Post link %s from user %s is incorrect',
            message.text,
            message.chat.id
        )


def queue_handler():
    log.info(
        '[Bot]: Starting thread for queue handler...'
    )
    while True:
        time.sleep(
            constants.QUEUE_FREQUENCY
        )
        message = database.get_message_from_queue(
            scheduled_time=datetime.now()
        )
        if message is not None:
            if message[5] == 'post':
                log.info(
                    '[Queue-thread-1] Starting handler for post url %s...',
                    message[3]
                )
                download_status = message[9]
                upload_status = message[10]
                # download the contents of an instagram post to a temporary folder
                if message[9] != 'completed':
                    #download_status = downloader.get_post_content(
                    #    shortcode=message[1]
                    #)
                    download_status = 'completed'
                    database.update_message_state_in_queue(
                        post_id=message[2],
                        state='processing download',
                        download_status=download_status,
                        upload_status=upload_status
                    )
                # upload the received content to the destination storage
                if message[10] != 'completed':
                    #upload_status = uploader.start_upload(
                    #    sub_dir_name=d_response['owner']
                    #)
                    upload_status = 'completed'
                    database.update_message_state_in_queue(
                        post_id=message[2],
                        state='processing upload',
                        download_status=download_status,
                        upload_status=upload_status
                        #upload_status=u_response['status']
                    )
                # mark item in queue as processed
                if download_status == 'completed' and upload_status == 'completed':
                    database.update_message_state_in_queue(
                        post_id=message[2],
                        state='processed',
                        download_status=download_status,
                        upload_status=upload_status
                    )
                    # send a message to the user with a link to the uploaded file
                    bot.edit_message_text(
                        chat_id=message[1],
                        message_id=message[7],
                        text=messages.render_template(
                            template_alias='post_downloaded',
                            post_id=message[2]
                        )
                    )
                    log.info(
                        '[Queue-thread-1] The URL of the post %s has been processed',
                        message[2]
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

    while True:
        log.info(
            '[Bot]: Starting bot %s...',
            constants.BOT_NAME
        )
        bot.polling()


if __name__ == "__main__":
    main()
