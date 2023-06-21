"""
This module interacts with the instagram api and uploads content to a temporary local directory.
Supports downloading the content of the post by link,
the entire content of posts in the account,
getting information about the account
and saving the history of already downloaded messages in the vault.
https://instaloader.github.io/module/instaloader.html
"""
import os
import instaloader
from logger import log


class Downloader:
    """
    The Instagram api instance is created by this class
    and contains a set of all the necessary posts
    for uploading content from Instagram accounts to local storage.
    """

    def __init__(
        self,
        auth: dict = None,
        settings: dict = None,
        vault: object = None
    ) -> None:
        """
        Method for create a new instagram api client instance.

        Args:
            :param auth (dict): dictionary with authorization parameters.
                :param username (str): username for authentication in the instagram api.
                :param password (str): password for authentication in the instagram api.
                :param sessionfile (str): the path to the session file of the instagram.
            :param settings (dict): dictionary with settings instaloader parameters.
                :param savepath (str): local directory for saving downloaded content.
                :param useragent (str): user-agent header.
            :param vault (object): instance of vault for recording or reading download history.

        Returns:
            None

        Examples:
            >>> downloader = Downloader(
                    auth={
                        'sessionfile': settings.instagram_session
                    },
                    settings={
                        'savepath': settings.temporary_dir,
                        'useragent': settings.instagram_useragent
                    },
                    vault=vault_client
                )
        """
        self.auth = auth
        self.settings = settings
        self.vault = vault

        # If the authorization data is not defined, read their values from the vault
        if (not self.auth['username']) or (self.auth['password']):
            self.auth['username'] = self.vault.read_secret(
                'configuration/instagram',
                'username'
            )
            self.auth['password'] = self.vault.read_secret(
                'configuration/instagram',
                'password'
            )

        self.instaloader = instaloader.Instaloader(
            quiet=True,
            user_agent=self.settings['useragent'],
            dirname_pattern=f"{settings['savepath']}/{{profile}}",
            filename_pattern='{profile}_{shortcode}_{filename}',
            download_pictures=True,
            download_videos=True,
            download_video_thumbnails=True,
            save_metadata=False,
            compress_json=True,
            post_metadata_txt_pattern=None,
            storyitem_metadata_txt_pattern=None,
            check_resume_bbd=True
        )
        try:
            if os.path.exists(self.settings['sessionfile']):
                self.instaloader.load_session_from_file(
                    self.auth['username'],
                    self.auth['sessionfile']
                )
                log.info(
                    '[class.%s] session file was load success',
                    __class__.__name__
                )
            else:
                self.instaloader.login(
                    self.auth['username'],
                    self.auth['password']
                )
                log.info(
                    '[class.%s] login with credentials was successful',
                    __class__.__name__
                )
                self.instaloader.save_session_to_file(self.auth['sessionfile'])
                log.info(
                    '[class.%s] new session file %s was save success',
                    __class__.__name__,
                    self.auth['sessionfile']
                )
        except instaloader.exceptions.LoginRequiredException as loginrequiredexception:
            log.warning(
                '[class.%s] login required: %s -> '
                'trying login with username/password',
                __class__.__name__,
                loginrequiredexception
            )
            try:
                self.instaloader.login(
                    self.auth['username'],
                    self.auth['password']
                )
                self.instaloader.save_session_to_file(self.auth['sessionfile'])
                log.info(
                    '[class.%s] new session file %s was save success',
                    __class__.__name__,
                    self.auth['sessionfile']
                )
            except instaloader.exceptions.BadCredentialsException as badcredentialsexception:
                log.error(
                    '[class.%s] bad credentials: %s',
                    __class__.__name__,
                    badcredentialsexception
                )
        except instaloader.exceptions.BadResponseException as badresponseexception:
            log.error(
                '[class.%s] bad response: %s',
                __class__.__name__,
                badresponseexception
            )
        except instaloader.exceptions.TooManyRequestsException as toomanyrequestsexception:
            log.error(
                '[class.%s] too many requests: %s',
                __class__.__name__,
                toomanyrequestsexception
            )

    def get_posts(
        self,
        username: str = None
    ) -> list | None:
        """
        Method for getting a list posts of instagram account.

        Args:
            :param username (str): instagram username to get a list of posts.

        Returns:
            (list) ['post_id_1', 'post_id_2', 'post_id_3']
                or
            None
        """
        try:
            profile = instaloader.Profile.from_username(
                self.instaloader.context,
                username
            )
            log.info(
                '[class.%s] the %s profile was read success',
                __class__.__name__,
                username
            )
            shortcodes_list = []
            for post in profile.get_posts():
                shortcodes_list.append(post.shortcode)
            return shortcodes_list
        except instaloader.exceptions.BadResponseException as badresponseexception:
            log.error(
                '[class.%s] bad response for username %s: %s',
                __class__.__name__,
                username,
                badresponseexception
            )
        except instaloader.exceptions.TooManyRequestsException as toomanyrequestsexception:
            log.error(
                '[class.%s] too many requests for username %s: %s',
                __class__.__name__,
                username,
                toomanyrequestsexception
            )
        return None

    def get_post_content(
        self,
        shortcode: str = None
    ) -> dict | None:
        """
        Method for getting the content of a post from a specified Instagram account.

        Args:
            :param shortcode (str): the shortcode is the ID of the record for downloading content.

        Returns:
            (dict) {
                    'post': shortcode,
                    'owner': post.owner_username,
                    'type': post.typename,
                    'status': 'downloaded'
                }
        """
        try:
            post = instaloader.Post.from_shortcode(
                self.instaloader.context,
                shortcode
            )
            self.instaloader.download_post(post, '')
            log.info(
                '[class.%s] the contents of the %s have been successfully downloaded '
                'to the temporary storage',
                __class__.__name__,
                shortcode
            )
            self.vault.write_secret(
                f'history/{post.owner_username}',
                shortcode,
                "downloaded"
            )
            return {
                'post': shortcode,
                'owner': post.owner_username,
                'type': post.typename,
                'status': 'downloaded'
            }
        except instaloader.exceptions.BadResponseException as badresponseexception:
            log.error(
                '[class.%s] bad response for post %s: %s',
                __class__.__name__,
                shortcode,
                badresponseexception
            )
        except instaloader.exceptions.TooManyRequestsException as toomanyrequestsexception:
            log.error(
                '[class.%s] too many requests for post %s: %s',
                __class__.__name__,
                shortcode,
                toomanyrequestsexception
            )
        return None

    def get_download_info(
        self,
        account_name: str = None
    ) -> dict | None:
        """
        Method for collecting all the necessary information
        to download all posts from the specified account.
        Checks the history of already uploaded posts
        and provides information for cyclic downloading.

        Args:
            :param account_name (str): instagram account name to check the uploaded history.

        Returns:
            (dict) {
                    "shortcodes_for_download": fresh_shortcodes,
                    "shortcodes_total_count": len(account_shortcodes),
                    "shortcodes_exist": len(history_shortcodes),
                    "shortcodes_exist_count": len(history_shortcodes.keys())
                }
        """
        try:
            log.info(
                '[class.%s] excluding shortcodes that are already downloaded...',
                __class__.__name__
            )
            # account_shortcodes - list of shortcodes received from instagram
            account_shortcodes = self.get_posts()
            # fresh_shortcodes - list of shortcodes that have not been downloaded yet
            fresh_shortcodes = []
            # history_shortcodes - list of shortcodes that have already been previously uploaded
            history_shortcodes = self.vault.read_secret(
                f'history/{account_name}'
            )
            for shortcode in account_shortcodes:
                if shortcode not in history_shortcodes.keys():
                    fresh_shortcodes.append(shortcode)
            log.info(
                '[class.%s] already downloaded shortcodes: %s\n'
                'fresh shortcodes: %s\n'
                'shortcodes for download: %s',
                __class__.__name__,
                history_shortcodes,
                account_shortcodes,
                fresh_shortcodes
            )
            return {
                "shortcodes_for_download": fresh_shortcodes,
                "shortcodes_total_count": len(account_shortcodes),
                "shortcodes_exist": len(history_shortcodes),
                "shortcodes_exist_count": len(history_shortcodes.keys())
            }
        except instaloader.exceptions.BadResponseException as badresponseexception:
            log.error(
                '[class.%s] bad response for post %s: %s',
                __class__.__name__,
                shortcode,
                badresponseexception
            )
        except instaloader.exceptions.TooManyRequestsException as toomanyrequestsexception:
            log.error(
                '[class.%s] too many requests for post %s: %s',
                __class__.__name__,
                shortcode,
                toomanyrequestsexception
            )
        return None
