
#         # download history
#         # we check the whole history instead of getting the owner by a short code to reduce
#         # the frequency of requests to the instagram api
#         for owner in vault.list_secrets(path='history/'):
#             for post in vault.read_secret(path=f"history/{owner}"):
#                 if post == shortcode and vault.read_secret(
#                     path=f"history/{owner}",
#                     key=post
#                 ) == 'downloaded':
#                     bot.send_message(
#                         chat_id=message.chat.id,
#                         text=messages.render_template(
#                             template_alias='post_already_downloaded',
#                             post_id=shortcode,
#                             owner=owner
#                         )
#                     )
#                     log.warning(
#                         '[%s] the post %s of the owner %s has already been downloaded, skipped.',
#                         __name__,
#                         post,
#                         owner
#                     )
#                     return

#         # download the contents of an instagram post to a temporary folder
#         d_response = downloader.get_post_content(
#             shortcode=shortcode
#         )
#         # upload the received content to the destination storage
#         u_response = uploader.start_upload(
#             sub_dir_name=d_response['owner']
#         )
#         bot.send_message(
#             chat_id=message.chat.id,
#             text=messages.render_template(
#                 'post_stats_info',
#                 post_id=shortcode,
#                 download_response=d_response,
#                 upload_response=u_response
#             )
#         )


# bot.message_handler(regexp=r"^https://(www\.)?instagram.com/(?!p/)(?!reel/).*$")
# def get_posts_account(
#      message: telegram.telegram_types.Message = None
# ) -> None:
#     """
#     A function for intercepting links sent to the bot to the Instagram profile.

#     Args:
#         :param message (telegram_types.Message): the message received by the bot.

#     Returns:
#         None
#     """
#     if users.check_permissions(
#         message.chat.id
#     ) == "allow":
#         log.info(
#             '[%s] starting handler for profile url %s...',
#             __name__,
#             message.text
#         )

#         editable_message = None
#         stats_message_id = None
#         account_name = message.text.split("/")[3].split("?")[0]
#         account_info = downloader.get_download_info(
#             account=account_name
#         )

#         bot.send_message(
#             message.chat.id,
#             messages.render_template(
#                 template_alias='account_info',
#                 account_name=account_name,
#                 shortcodes_count=account_info['shortcodes_total_count']
#             )
#         )

#         for shortcode in account_info['shortcodes_for_download']:
#             # download the contents of an instagram post to a temporary folder
#             d_response = downloader.get_post_content(
#                 shortcode=shortcode
#             )
#             # upload the received content to the destination storage
#             _ = uploader.start_upload(
#                 sub_dir_name=d_response['owner']
#             )
#             # render progressbar
#             progressbar = messages.render_progressbar(
#                 total_count=account_info['shortcodes_total_count'],
#                 current_count=account_info['shortcodes_exist_count']
#             )
#             account_info['shortcodes_exist_count'] = account_info['shortcodes_exist_count'] + 1
#             stats_response = messages.render_template(
#                 template_alias='account_stats_progress',
#                 account_name=account_name,
#                 posts_downloaded=account_info['shortcodes_exist_count'],
#                 posts_count=account_info['shortcodes_total_count'],
#                 progressbar=progressbar
#             )
#             # check whether a message with stats has already been sent and whether we can edit it
#             if not editable_message:
#                 stats_message_id = bot.send_message(
#                     chat_id=message.chat.id,
#                     text=stats_response
#                 ).id
#                 editable_message = True
#             elif editable_message:
#                 bot.edit_message_text(
#                     text=stats_response,
#                     chat_id=message.chat.id,
#                     message_id=stats_message_id
#                 )

#         # when all messages are uploaded send a response with statistics
#         bot.edit_message_text(
#             text=messages.render_template(
#                 template_alias='account_stats_done',
#                 posts_downloaded=account_info['shortcodes_exist_count'],
#                 posts_count=account_info['shortcodes_total_count'],
#                 account_name=account_name,
#                 progressbar=messages.render_progressbar(
#                     total_count=account_info['shortcodes_total_count'],
#                     current_count=account_info['shortcodes_exist_count']
#                 )
#             ),
#             chat_id=message.chat.id,
#             message_id=stats_message_id
#         )
#         log.info(
#             '[%s] all available posts from account %s has been downloaded',
#             __name__,
#             account_name
#         )


