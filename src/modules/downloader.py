# pylint: disable=duplicate-code
"""
This module interacts with the instagram api and uploads content to a temporary directory.
Supports downloading the content of the post by link and getting information about the account.
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
    An Instagram API instance is created by this class and contains a set of all the necessary methods
    to upload content from Instagram to a temporary directory.
    """
    def __init__(
        self,
        configuration: dict = None,
        vault: object = None
    ) -> None:
        """
        The method for create a new Instagram API client instance.

        Args:
            :param configuration (dict): dictionary with configuration parameters for Instagram API communication.
                :param username (str): username for authentication in the instagram api.
                :param password (str): password for authentication in the instagram api.
                :param login-method (str): method for authentication in the instagram api. Can be: 'session', 'password', 'anonymous'.
                :param session-file (str): the path for saving the session file.
                :param user-agent (str): user-agent header.
                :param fatal-status-codes (list): list of fatal status codes, this causes the thread executing this module's code to crash.
                :param iphone-support (bool): enable or disable iphone http headers.
                :param session-base64 (str): base64 encoded session file.
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
            ...     'session-base64': '<base64_encoded_session_file>',
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
            self.configuration = vault.kv2engine.read_secret(path='configuration/downloader-api')
        else:
            raise FailedCreateDownloaderInstance(
                "Failed to initialize the Downloader instance."
                "Please check the configuration in class argument or the secret with the configuration in the Vault."
            )
        log.info('[Downloader]: creating a new instance of the Downloader...')
        self.instaloader = instaloader.Instaloader(
            quiet=True,
            user_agent=self.configuration.get('user-agent', None),
            iphone_support=self.configuration.get('iphone-support', None),
            dirname_pattern='data/{profile}',
            filename_pattern='{profile}_{shortcode}_{filename}',
            download_pictures=True,
            download_videos=True,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
            post_metadata_txt_pattern=None,
            storyitem_metadata_txt_pattern=None,
            check_resume_bbd=True,
            fatal_status_codes=literal_eval(self.configuration.get('fatal-status-codes', '[]'))
        )
        auth_status = self._login()
        log.info(
            '[Downloader]: downloader instance created successfully: %s in %s',
            auth_status, self.configuration['username']
        )

    def _login(self) -> Union[str, None]:
        """
        The method for authentication in Instagram API.

        Args:
            None
        Returns:
            (str) logged_in
                or
            None
        """
        if self.configuration['login-method'] == 'session':
            # If session-base64 defined in the configuration, then decode and save the session file.
            if self.configuration.get('session-base64', None):
                with open(self.configuration['session-file'], 'wb') as file:
                    file.write(base64.b64decode(self.configuration['session-base64']))
            # Otherwise, it expects the session file to be in the specified path.
            self.instaloader.load_session_from_file(
                self.configuration['username'],
                self.configuration['session-file']
            )
            log.info('[Downloader]: session file %s was load success', self.configuration['session-file'])
            return 'logged_in'

        if self.configuration['login-method'] == 'password':
            self.instaloader.login(
                self.configuration['username'],
                self.configuration['password']
            )
            self.instaloader.save_session_to_file(self.configuration['session-file'])
            log.info(
                '[Downloader]: login with password was successful. Save session in %s',
                self.configuration['sessionfile']
            )
            return 'logged_in'

        if self.configuration['login-method'] == 'anonymous':
            log.warning('[Downloader]: initialization without authentication into an account (anonymous)')
            return None

        raise FailedAuthInstaloader(
            "Failed to authenticate the Instaloader instance. Please check the configuration in the Vault or the class argument."
        )

    def get_post_content(
        self,
        shortcode: str = None
    ) -> Union[dict, None]:
        """
        The method for getting the content of a post from a specified Post ID.

        Args:
            :param shortcode (str): the ID of the record for downloading content.

        Returns:
            (dict) {
                    'post': shortcode,
                    'owner': owner,
                    'type': typename,
                    'status': 'completed'
                }
        """
        log.info('[Downloader]: downloading the contents of the post %s...', shortcode)
        try:
            post = instaloader.Post.from_shortcode(self.instaloader.context, shortcode)
            self.instaloader.download_post(post, '')
            log.info('[Downloader]: the contents of the post %s have been successfully downloaded', shortcode)
            status = 'completed'
            owner = post.owner_username
            typename = post.typename
        except instaloader.exceptions.BadResponseException as error:
            log.error('[Downloader]: error downloading post content: %s', error)
            if "Fetching Post metadata failed" in str(error):
                status = 'source_not_found'
                owner = 'undefined'
                typename = 'undefined'
                log.warning('[Downloader]: post %s not found, perhaps it was deleted. Message will be marked as processed.', shortcode)
            else:
                raise instaloader.exceptions.BadResponseException(error)

        return {
            'post': shortcode,
            'owner': owner,
            'type': typename,
            'status': status
        }
