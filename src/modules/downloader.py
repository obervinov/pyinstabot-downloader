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
                :param anonymous (bool): access to open profiles without logging in to an account.
                                         only for tests.
            :param settings (dict): dictionary with settings instaloader parameters.
                :param savepath (str): local directory for saving downloaded content.
                :param useragent (str): user-agent header.
            :param vault (object): instance of vault for recording or reading download history.

        Returns:
            None

        Examples:
            >>> DOWNLOADER_INSTANCE = Downloader(
                    auth={
                        'anonymous': true
                    },
                    settings={
                        'savepath': TEMPORARY_DIR,
                        'useragent': INSTAGRAM_USERAGENT
                    },
                    vault=VAULT_CLIENT
                )
            >>> DOWNLOADER_INSTANCE = Downloader(
                    auth={
                        'sessionfile': INSTAGRAM_SESSION
                    },
                    settings={
                        'savepath': TEMPORARY_DIR,
                        'useragent': INSTAGRAM_USERAGENT
                    },
                    vault=VAULT_CLIENT
                )
            >>> DOWNLOADER_INSTANCE = Downloader(
                    auth={
                        'username': INSTAGRAM_USERNAME,
                        'password': INSTAGRAM_PASSWORD
                    },
                    settings={
                        'savepath': TEMPORARY_DIR,
                        'useragent': INSTAGRAM_USERAGENT
                    },
                    vault=VAULT_CLIENT
                )
        """
        self.auth = auth
        self.settings = settings
        self.vault = vault
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
            check_resume_bbd=True,
            fatal_status_codes=[400, 429, 500]
        )

        if self.auth.get('anonymous'):
            auth_status = self._login(
                method='anonymous'
            )
        elif os.path.exists(
            self.auth.get('sessionfile')
        ):
            auth_status = self._login(
                method='session'
            )
        else:
            auth_status = self._login(
                method='password'
            )
        log.info(
            '[class.%s] downloader instance init with account %s: %s',
            __class__.__name__,
            self.auth['username'],
            auth_status
        )

    def _login(
        self,
        method: str = None
    ) -> str | None:
        """
        A method for authentication in instagram api.

        Args:
            :param method (str): authentication method 'password', 'session' or 'anonymous'.

        Returns:
            (str) success
                or
            None
        """
        if not self.auth.get('username') or not self.auth.get('anonymous'):
            self.auth['username'] = self.vault.read_secret(
                'configuration/instagram',
                'username'
            )

        if method == 'session':
            self.instaloader.load_session_from_file(
                self.auth['username'],
                self.auth['sessionfile']
            )
            log.info(
                '[class.%s] session file was load success',
                __class__.__name__
            )
            return 'success'

        if method == 'password':
            if not self.auth.get('password'):
                self.auth['password'] = self.vault.read_secret(
                    'configuration/instagram',
                    'password'
                )
            self.instaloader.login(
                self.auth['username'],
                self.auth['password']
            )
            self.instaloader.save_session_to_file(
                self.auth['sessionfile']
            )
            log.info(
                '[class.%s] login with password was successful. Save session in %s',
                __class__.__name__,
                self.auth['sessionfile']
            )
            return 'success'

        if method == 'anonymous':
            log.warning(
                '[class.%s] initialization without logging into an account (anonymous)',
                __class__.__name__
            )
            return None

        return None

    def get_posts(
        self,
        username: str = None
    ) -> list | None:
        """
        A method for getting a list posts of instagram account.

        Args:
            :param username (str): instagram account profile name.

        Returns:
            (list) ['post_id_1', 'post_id_2', 'post_id_3']
                or
            None
        """
        posts_list = []
        profile = instaloader.Profile.from_username(
            self.instaloader.context,
            username
        )
        log.info(
            '[class.%s] the %s profile was read success',
            __class__.__name__,
            username
        )
        for post in profile.get_posts():
            posts_list.append(post.shortcode)

        return posts_list

    def get_post_content(
        self,
        shortcode: str = None
    ) -> dict | None:
        """
        A method for getting the content of a post from a specified Instagram account.

        Args:
            :param shortcode (str): the ID of the record for downloading content.

        Returns:
            (dict) {
                    'post': shortcode,
                    'owner': post.owner_username,
                    'type': post.typename,
                    'status': 'downloaded'
                }
        """
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

    def get_download_info(
        self,
        account: str = None
    ) -> dict | None:
        """
        A method for collecting all the necessary information
        to download all posts from the specified account.
        Checks the history of already uploaded posts
        and provides information for cyclic downloading.

        Args:
            :param account (str): instagram account name to check the uploaded history.

        Returns:
            (dict) {
                    "shortcodes_for_download": fresh_shortcodes,
                    "shortcodes_total_count": len(account_shortcodes),
                    "shortcodes_exist": len(history_shortcodes),
                    "shortcodes_exist_count": len(history_shortcodes.keys())
                }
        """
        log.info(
            '[class.%s] excluding shortcodes that are already downloaded...',
            __class__.__name__
        )
        # account_shortcodes - list of shortcodes received from instagram
        account_shortcodes = self.get_posts(
            username=account
        )
        # fresh_shortcodes - list of shortcodes that have not been downloaded yet
        fresh_shortcodes = []
        # history_shortcodes - dict of shortcodes that have already been previously uploaded
        try:
            history_shortcodes = self.vault.read_secret(
                f'history/{account}'
            )
        # pylint: disable=W0718
        # will be fixed after https://github.com/obervinov/vault-package/issues/31
        except Exception as secret_not_found:
            history_shortcodes = {}
            log.warning(
                '[class.%s] secret history/%s does not exist: %s',
                __class__.__name__,
                account,
                secret_not_found
            )
        for shortcode in account_shortcodes:
            if shortcode not in history_shortcodes.keys():
                fresh_shortcodes.append(shortcode)
        log.info(
            '[class.%s] account metadata:\n'
            'already downloaded shortcodes: %s\n'
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
