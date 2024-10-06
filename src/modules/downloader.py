# pylint: disable=duplicate-code
"""
This module interacts with the instagram api and uploads content to a temporary directory.
Supports downloading the content of the post by link and getting information about the account.
https://github.com/subzeroid/instagrapi
"""
import os
import time
import random
from typing import Union
from pathlib import Path
from instagrapi import Client
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
                :param session-file (str): path to the session file for authentication in the instagram api.
                :param delay-requests (int): delay between requests.
                :param 2fa-code (str): two-factor authentication code.
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

        log.info('[Downloader]: Creating a new instance...')
        self.client = Client()
        auth_status = self._login()

        if auth_status == 'logged_in':
            log.info('[Downloader]: Instance created successfully with account %s', self.configuration['username'])
        else:
            raise FailedAuthInstaloader("Failed to authenticate the Instaloader instance.")

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
        log.info('[Downloader]: Authentication in the Instagram API...')
        if self.configuration['2fa-code']:
            login_args = {
                'username': self.configuration['username'],
                'password': self.configuration['password'],
                'verification_code': self.configuration['2fa-code']
            }
        else:
            login_args = {
                'username': self.configuration['username'],
                'password': self.configuration['password']
            }
        if os.path.exists(self.configuration['session-file']):
            self.client.load_settings(self.configuration['session-file'])
            self.client.login(**login_args)
        else:
            self.client.login(**login_args)
            self.client.dump_settings(self.configuration['session-file'])
        log.info('[Downloader]: Authentication in the Instagram API was successful.')
        return 'logged_in'

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
        log.info('[Downloader]: Downloading the contents of the post %s...', shortcode)
        try:
            media_pk = self.client.media_pk_from_code(code=shortcode)
            media_info = self.client.media_info(media_pk=media_pk).dict()

            path = Path(f"data/{media_info['user']['username']}")
            os.makedirs(path, exist_ok=True)

            for resource in media_info['resources']:
                time.sleep(random.randint(1, self.configuration['delay-requests']))
                if resource['media_type'] == 1:
                    path = self.client.photo_download(media_pk=media_pk, folder=path)
                elif resource['media_type'] == 2 and media_info['product_type'] == 'feed':
                    path = self.client.video_download(media_pk=media_pk, folder=path)
                elif resource['media_type'] == 2 and media_info['product_type'] == 'igtv':
                    path = self.client.igtv_download(media_pk=media_pk, folder=path)
                elif resource['media_type'] == 2 and media_info['product_type'] == 'clips':
                    path = self.client.clip_download(media_pk=media_pk, folder=path)
                else:
                    log.warning('[Downloader]: The media type is not supported for download: %s', media_info)
                    path = None

                if path:
                    log.info('[Downloader]: The contents of the post %s have been successfully downloaded', shortcode)
                    response = {
                        'post': shortcode,
                        'owner': media_info['user']['username'],
                        'type': {media_info['product_type'] if media_info['product_type'] else 'photo'},
                        'status': 'completed'
                    }
                else:
                    log.error('[Downloader]: Error downloading post content: %s', media_info)
                    response = {
                        'post': shortcode,
                        'owner': media_info['user']['username'],
                        'type': {media_info['product_type'] if media_info['product_type'] else 'photo'},
                        'status': 'failed'
                    }
            return response

        # pylint: disable=broad-except
        except Exception as error:
            log.error('[Downloader]: Error downloading post content: %s', error)
            return None
