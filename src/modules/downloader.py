# pylint: disable=duplicate-code
"""
This module interacts with the instagram api and uploads content to a temporary directory.
Supports downloading the content of the post by link and getting information about the account.
https://github.com/subzeroid/instagrapi
"""
import os
from typing import Union
from pathlib import Path
from instagrapi import Client
from instagrapi.exceptions import LoginRequired
from logger import log
from .exceptions import WrongVaultInstance, FailedCreateDownloaderInstance, FailedAuthInstagram


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
                :param 2fa-enabled (bool): two-factor authentication enabled.
                :param 2fa-seed (str): seed for two-factor authentication (secret key).
                :param locale (str): locale for requests.
                :param country-code (str): country code for requests.
                :param timezone-offset (int): timezone offset for requests.
                :param user-agent (str): user agent for requests.
                :param proxy-dsn (str): proxy dsn for requests.
            :param vault (object): instance of vault for reading configuration downloader-api.

        Returns:
            None

        Attributes:
            :attribute configuration (dict): dictionary with configuration parameters for instagram api communication.
            :attribute client (object): instance of the instagram api client.

        Examples:
            >>> configuration = {
            ...     'username': 'my_username',
            ...     'password': 'my_password',
            ...     'session-file': 'data/session.json',
            ...     'delay-requests': 1,
            ...     '2fa-enabled': False,
            ...     '2fa-seed': 'my_seed_secret',
            ...     'locale': 'en_US',
            ...     'country-code': '1',
            ...     'timezone-offset': 10800,
            ...     'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            ...     'proxy-dsn': 'http://localhost:8080'
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

        log.info('[Downloader]: Configuring client settings...')
        self.client.delay_range = [1, int(self.configuration['delay-requests'])]
        self.client.set_locale(locale=self.configuration['locale'])
        self.client.set_country_code(country_code=int(self.configuration['country-code']))
        self.client.set_timezone_offset(seconds=int(self.configuration['timezone-offset']))
        self.client.set_user_agent(user_agent=self.configuration['user-agent'])
        self.client.set_proxy(dsn=self.configuration.get('proxy-dsn', None))

        auth_status = self._login()
        if auth_status == 'logged_in':
            log.info('[Downloader]: Instance created successfully with account %s', self.configuration['username'])
        else:
            raise FailedAuthInstagram("Failed to authenticate the Instaloader instance.")

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

        if self.configuration['2fa-enabled']:
            totp_code = self.client.totp_generate_code(seed=self.configuration['2fa-seed'])
            log.info('[Downloader]: Two-factor authentication is enabled. TOTP code: %s', totp_code)
            login_args = {
                'username': self.configuration['username'],
                'password': self.configuration['password'],
                'verification_code': totp_code
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

        try:
            self.client.get_timeline_feed()
        except LoginRequired:
            log.error('[Downloader]: Authentication in the Instagram API failed.')
            old_session = self.client.get_settings()
            self.client.set_settings({})
            self.client.set_uuids(old_session["uuids"])
            self.client.login(**login_args)

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

            if media_info['media_type'] == 1:
                self.client.photo_download(media_pk=media_info['pk'], folder=path)

            elif media_info['media_type'] == 2 and media_info['product_type'] == 'feed':
                self.client.video_download(media_pk=media_info['pk'], folder=path)

            elif media_info['media_type'] == 2 and media_info['product_type'] == 'clips':
                self.client.clip_download(media_pk=media_info['pk'], folder=path)

            elif media_info['media_type'] == 2 and media_info['product_type'] == 'igtv':
                self.client.igtv_download(media_pk=media_info['pk'], folder=path)

            elif media_info['media_type'] == 8:
                self.client.album_download(media_pk=media_info['pk'], folder=path)

            else:
                log.error('[Downloader]: The media type is not supported for download: %s', media_info)
                status = "not_supported"

            if os.listdir(path):
                log.info('[Downloader]: The contents of the post %s have been successfully downloaded', shortcode)
                response = {
                    'post': shortcode,
                    'owner': media_info['user']['username'],
                    'type': {media_info['product_type'] if media_info['product_type'] else 'photo'},
                    'status': {status if status else 'completed'}
                }

            else:
                log.error('[Downloader]: Temporary directory is empty: %s', path)
                response = {
                    'post': shortcode,
                    'owner': media_info['user']['username'],
                    'type': {media_info['product_type'] if media_info['product_type'] else 'photo'},
                    'status': {status if status else 'failed'}
                }

            return response

        # pylint: disable=broad-except
        # Temporary general exception for migration to the new module.
        # Will be replaced by specific exceptions after v3.0.0
        except Exception as error:
            log.error('[Downloader]: Error downloading post content: %s\n%s', error, media_info)
            return None
