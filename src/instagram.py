# THIS FILE FROM INSTGRAM API #
# Importing modules #
# https://instaloader.github.io/module/instaloader.html
import instaloader
import time
import datetime
from logger import log
from src.progressbar import ProgressBar
from ast import Str


class InstagramDownloader:

    def __init__(self,
                 Vault=None,
                 user: Str = None,
                 password: Str = None,
                 sessionfile: Str = None,
                 bot_name: Str = None,
                 Dropbox=None,
                 Telebot=None
                 ) -> None:

        self.Vault = Vault
        self.Dropbox = Dropbox
        self.Telebot = Telebot
        self.sessionfile = sessionfile
        self.bot_name = bot_name

        instaloaderObject = instaloader.Instaloader(
            sleep=True,
            quiet=True,
            user_agent=None,
            dirname_pattern="temp-data/{profile}_{shortcode}",
            filename_pattern="{profile}_{shortcode}_{filename}",
            download_pictures=True,
            download_videos=True,
            download_video_thumbnails=True,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=True,
            post_metadata_txt_pattern=None,
            storyitem_metadata_txt_pattern=None,
            max_connection_attempts=3,
            request_timeout=300.0,
            rate_controller=None,
            resume_prefix='iterator',
            check_resume_bbd=True,
            slide=None)

        try:
            instaloaderObject.load_session_from_file(user, sessionfile)
            self.instaloaderObject = instaloaderObject
            log.info(f"[class.{__class__.__name__}] load session file successful")

        except Exception as ex:
            log.warning(f"[class.{__class__.__name__}] load session file error: {ex}")

            try:
                instaloaderObject.login(user, password)
                self.instaloaderObject = instaloaderObject
                log.info("[class.{__class__.__name__}] login with username/password successful")

                log.info(f"[class.{__class__.__name__}] saving new session in file: {sessionfile}")
                instaloaderObject.save_session_to_file(sessionfile)

            except Exception as ex:
                log.error(f"[class.{__class__.__name__}] faild login with username/password: {ex}")


    def get_posts_list(self, username: str = None):

        try:
            profile = instaloader.Profile.from_username(self.instaloaderObject.context, username)
            log.info(f"[class.{__class__.__name__}] reading profile {username} was successful")

            posts = profile.get_posts()
            self.posts_count = posts.count
            log.info(
                f"[class.{__class__.__name__}] "
                f"reading list of posts from account {username} "
                f"was successful"
                )

            shortcodes_list = list()
            shortcodes_list_exist = list()
            profile_path = f"{self.bot_name}-data/{username}"

            log.info(f"[class.{__class__.__name__}] reading history in vault for {username} ...")
            shortcodes = self.Vault.vault_read_secrets(profile_path)

            if "InvalidPath" not in shortcodes:
                # Checking the status of already uploaded posts
                log.info(
                    f"[class.{__class__.__name__}] "
                    f"excluding shortcodes already downloaded..."
                    )
                for key, value in shortcodes.items():
                    if value == 'success':
                        shortcodes_list_exist.append(key)

                # Exclude already uploaded posts from the list
                log.info(
                    f"[class.{__class__.__name__}] "
                    f"building list of shortcodes for downloaded..."
                    )
                for post in posts:
                    if post.shortcode not in shortcodes_list_exist:
                        shortcodes_list.append(post.shortcode)

            log.info(
                f"[class.{__class__.__name__}] "
                f"building list of posts for downloaded was be done"
                )
            return shortcodes_list

        except Exception as ex:
            log.error(
                f"[class.{__class__.__name__}] "
                f"readed posts from account {username} "
                f"faild {ex}"
                )


    def download_post(self, shortcode: str = None):

        # Find and download post content
        try:
            post = instaloader.Post.from_shortcode(self.instaloaderObject.context, shortcode)
            owner_name = str(post.owner_username)
            save_dir_name = f"temp-data/{owner_name}_{shortcode}"

            # Progressbar options for vault (dict for statistics)
            vault_path = f"{self.bot_name}-data/" + owner_name

            self.instaloaderObject.download_post(post, '')
            log.info(
                f"[class.{__class__.__name__}] "
                f"content of post {shortcode} "
                f"successful downloaded in temp storage"
                )

            status, response = self.Dropbox.upload_file(save_dir_name, owner_name)

            # recording statistics on download into vault
            self.Vault.vault_put_secrets(vault_path, shortcode, status)

            return response

        except Exception as ex:
            log.error(
                f"[class.{__class__.__name__}] "
                f"content by post {shortcode} "
                f"faild downloaded: {ex}"
                )
            self.Vault.vault_put_secrets(vault_path, shortcode, 'faild')


    def download_all_posts(self,
                           username: str = None,
                           ratelimit_timeout: int = 30,
                           ratelimit_max_timeout: int = 1800,
                           chat_id: str = None
                           ):

        # unchangeable minimum timeout value
        # to be reset to default value when ratelimit_max_timeout is reached
        ratelimit_timeout_default = ratelimit_timeout
        # progressbar and stats options/vars
        message_object_stats = ''
        editable_message_bot = 0

        shortcodes_list = self.get_posts_list(username)

        answer = (
            f"\u2B50 Reading posts from account <b>{username}</b> successful.\n"
            f"\U0001F303 Posts count: <b>{self.posts_count}</b>\n"
            f"\U0001F6A6 Ratelimit timings: "
            f"<i>min {ratelimit_timeout}s - max {ratelimit_max_timeout}s</i>"
        )
        self.Telebot.send_message(chat_id, answer)

        for shortcode in shortcodes_list:
            self.download_post(shortcode)

            Progressbar = ProgressBar(self.Vault, self.bot_name, username)
            response = Progressbar.get(self.posts_count, "in_progress")

            # checking the condition whether the first message with statistics has already been sent
            # for its subsequent editing
            if editable_message_bot == 0:
                message_object_stats = self.Telebot.send_message(chat_id, response)
                editable_message_bot = 1
            else:
                self.Telebot.edit_message_text(response, chat_id, message_object_stats.id)

            # pause downloaded for ratelimit
            log.warning(
                f"[class.{__class__.__name__}] "
                f"ratelimit aplied in {datetime.datetime.now().strftime('%H:%M:%S')}: "
                f"{ratelimit_timeout}"
                )
            time.sleep(ratelimit_timeout)

            # reset timeout value to default if value too large (4600s/50m)
            if ratelimit_timeout > ratelimit_max_timeout:
                ratelimit_timeout = ratelimit_timeout_default

            # we increase the timeout so as not to get into the blacklist of instagram
            ratelimit_timeout = int(ratelimit_timeout * 1.1)

        Finally_Progressbar = ProgressBar(self.Vault, self.bot_name, username)
        finally_response = Finally_Progressbar.get(self.posts_count, "finally")

        log.info(
            f"[class.{__class__.__name__}] "
            f"all available posts from account {username} "
            f"has been downloaded"
            )
        self.Telebot.edit_message_text(finally_response, chat_id, message_object_stats.id)
