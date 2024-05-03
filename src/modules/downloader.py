# pylint: disable=R0801
"""
This module interacts with the instagram api and uploads content to a temporary local directory.
Supports downloading the content of the post by link,
the entire content of posts in the account,
getting information about the account
and saving the history of already downloaded messages in the vault.
https://instaloader.github.io/module/instaloader.html
"""
from typing import Union
from ast import literal_eval
import base64
import instaloader
from logger import log
from .exceptions import WrongVaultInstance, FailedCreateDownloaderInstance, FailedAuthInstaloader


# pylint: disable=too-few-public-methods
class Downloader:
    """
    The Instagram api instance is created by this class
    and contains a set of all the necessary posts
    for uploading content from Instagram accounts to local storage.
    """

    def __init__(
        self,
        configuration: dict = None,
        vault: object = None
    ) -> None:
        """
        The method for create a new instagram api client instance.

        Args:
            :param configuration (dict): dictionary with configuration parameters for instagram api communication.
                :param username (str): username for authentication in the instagram api.
                :param password (str): password for authentication in the instagram api.
                :param login-method (str): method for authentication in the instagram api. Can be: 'session', 'password', 'anonymous'.
                :param session-file (str): the path to the session file of the instagram.
                :param enabled (bool): enable or disable the downloader instance.
                :param user-agent (str): user-agent header.
            :param vault (object): instance of vault for reading configuration downloader-api.

        Returns:
            None

        Attributes:
            :attribute configuration (dict): dictionary with configuration parameters for instagram api communication.
            :attribute instaloader (object): instance of the instaloader class for working

        Examples:
            >>> configuration = {
            ...     'username': 'my_username',
            ...     'password': 'my_password',
            ...     'login-method': 'session',
            ...     'session-file': '/path/to/session/file',
            ...     'enabled': True,
            ...     'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
            ... }
            >>> vault = Vault()
            >>> downloader = Downloader(configuration, vault)
        """
        if not vault:
            raise WrongVaultInstance("Wrong vault instance, you must pass the vault instance to the class argument.")

        if configuration:
            self.configuration = configuration
        elif not configuration:
            self.configuration = vault.read_secret(path='configuration/downloader-api')
        else:
            raise FailedCreateDownloaderInstance(
                "Failed to initialize the Downloader instance."
                "Please check the configuration in class argument or the secret with the configuration in the Vault."
            )
        log.info('[class.%s] Try to create a new instance of the Downloader class', __class__.__name__)
        self.instaloader = instaloader.Instaloader(
            quiet=True,
            user_agent=self.configuration.get('user-agent', None),
            iphone_support=self.configuration.get('iphone-support', None),
            dirname_pattern='data/{profile}',
            filename_pattern='{profile}_{shortcode}_{filename}',
            download_pictures=True,
            download_videos=True,
            download_video_thumbnails=True,
            save_metadata=False,
            compress_json=True,
            post_metadata_txt_pattern=None,
            storyitem_metadata_txt_pattern=None,
            check_resume_bbd=True,
            fatal_status_codes=literal_eval(self.configuration.get('fatal-status-codes', '[]'))
        )
        auth_status = self._login()
        log.info('[class.%s] Downloader instance init with account %s: %s', __class__.__name__, self.configuration['username'], auth_status)

    def _login(self) -> Union[str, None]:
        """
        The method for authentication in instagram api.

        Args:
            None
        Returns:
            (str) logged_in
                or
            None
        """
        if self.configuration['login-method'] == 'session':
            if self.configuration.get('session-base64', None):
                with open(self.configuration['session-file'], 'r', encoding='utf-8') as file:
                    file.write(base64.b64decode(self.configuration['session-base64']).decode('utf-8'))
            self.instaloader.load_session_from_file(
                self.configuration['username'],
                self.configuration['session-file']
            )
            log.info('[class.%s] session file %s was load success', __class__.__name__, self.configuration['session-file'])
            return 'logged_in'

        if self.configuration['login-method'] == 'password':
            self.instaloader.login(
                self.configuration['username'],
                self.configuration['password']
            )
            self.instaloader.save_session_to_file(self.configuration['session-file'])
            log.info('[class.%s] login with password was successful. Save session in %s', __class__.__name__, self.configuration['sessionfile'])
            return 'logged_in'

        if self.configuration['login-method'] == 'anonymous':
            log.warning('[class.%s] initialization without logging into an account (anonymous)', __class__.__name__)
            return None

        raise FailedAuthInstaloader("Failed to authenticate the Instaloader instance. Please check the configuration in the Vault.")

    def get_post_content(
        self,
        shortcode: str = None
    ) -> Union[dict, None]:
        """
        The method for getting the content of a post from a specified Instagram account.

        Args:
            :param shortcode (str): the ID of the record for downloading content.

        Returns:
            (dict) {
                    'post': shortcode,
                    'owner': post.owner_username,
                    'type': post.typename,
                    'status': 'completed'
                }
        """
        log.info('[class.%s]: downloading the contents of the post %s...', __class__.__name__, shortcode)
        post = instaloader.Post.from_shortcode(
            self.instaloader.context,
            shortcode
        )
        self.instaloader.download_post(post, '')
        log.info('[class.%s]: the contents of the post %s have been successfully downloaded', __class__.__name__, shortcode)
        metadata = {
            'post': shortcode,
            'owner': post.owner_username,
            'type': post.typename,
            'status': 'completed'
        }
        return metadata
