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
from urllib3.exceptions import ReadTimeoutError
from requests.exceptions import ConnectionError as RequestsConnectionError
from instagrapi import Client
from instagrapi.exceptions import LoginRequired, ClientRequestTimeout, MediaNotFound, MediaUnavailable
from logger import log
from .exceptions import WrongVaultInstance, FailedCreateDownloaderInstance, FailedAuthInstagram, FailedDownloadPost


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
                :param request-timeout (int): request timeout for requests.
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
            ...     'request-timeout': 10
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
        self.client.request_timeout = int(self.configuration['request-timeout'])
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

        self.download_methods = {
            (1, 'any'): self.client.photo_download,
            (2, 'feed'): self.client.video_download,
            (2, 'clips'): self.client.clip_download,
            (2, 'igtv'): self.client.igtv_download,
            (8, 'any'): self.client.album_download
        }

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

    def get_post_content(self, shortcode: str = None, error_count: int = 0) -> Union[dict, None]:
        """
        The method for getting the content of a post from a specified Post ID.

        Args:
            :param shortcode (str): the ID of the record for downloading content.
            :param error_count (int): the number of errors that occurred during the download.

        Returns:
            (dict) {
                    'post': shortcode,
                    'owner': owner,
                    'type': typename,
                    'status': 'completed'
                }
        """
        if error_count > 3:
            log.error('[Downloader]: The number of errors exceeded the limit: %s', error_count)
            raise FailedDownloadPost("The number of errors exceeded the limit.")

        log.info('[Downloader]: Downloading the contents of the post %s...', shortcode)
        try:
            media_pk = self.client.media_pk_from_code(code=shortcode)
            media_info = self.client.media_info(media_pk=media_pk).dict()
            media_type = media_info['media_type']
            product_type = media_info.get('product_type')
            key = (media_type, 'any' if media_type in (1, 8) else product_type)
            download_method = self.download_methods.get(key)

            path = Path(f"data/{media_info['user']['username']}")
            os.makedirs(path, exist_ok=True)
            status = None

            if download_method:
                download_method(media_pk=media_pk, folder=path)
                status = "completed"
            else:
                log.error('[Downloader]: The media type is not supported for download: %s', media_info)
                status = "not_supported"

            if os.listdir(path):
                log.info('[Downloader]: The contents of the post %s have been successfully downloaded', shortcode)
                response = {
                    'post': shortcode,
                    'owner': media_info['user']['username'],
                    'type': media_info['product_type'] if media_info['product_type'] else 'photo',
                    'status': status if status else 'completed'
                }
            else:
                log.error('[Downloader]: Temporary directory is empty: %s', path)
                response = {
                    'post': shortcode,
                    'owner': media_info['user']['username'],
                    'type': media_info['product_type'] if media_info['product_type'] else 'photo',
                    'status': status if status else 'failed'
                }

        except (MediaUnavailable, MediaNotFound) as error:
            log.warning('[Downloader]: Post %s not found, perhaps it was deleted. Message will be marked as processed:\n%s', shortcode, error)
            response = {
                'post': shortcode,
                'owner': 'undefined',
                'type': 'undefined',
                'status': 'source_not_found'
            }

        except (ReadTimeoutError, RequestsConnectionError, ClientRequestTimeout) as error:
            pause = random.randint(self.configuration['delay-requests'] * 3, self.configuration['delay-requests'] * 30)
            log.error('[Downloader]: Timeout error downloading post content: %s\n%s\nWaiting %s seconds...', error, shortcode, pause)
            time.sleep(pause)
            self.get_post_content(shortcode=shortcode, error_count=error_count + 1)

        # Temporary general exception for migration to the new module.
        # Will be replaced by specific exceptions after v3.0.0
        # pylint: disable=broad-exception-caught
        except Exception as error:
            log.error('[Downloader]: Error downloading post content: %s (%s)\n%s', error, type(error), media_info)
            raise FailedDownloadPost("General error downloading post content.") from error

        return response
