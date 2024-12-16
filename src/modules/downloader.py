# pylint: disable=duplicate-code
"""
This module interacts with the instagram api and uploads content to a temporary directory.
Supports downloading the content of the post by link and getting information about the account.
https://github.com/subzeroid/instagrapi
"""
import os
import time
import json
import random
from pathlib import Path
from urllib3.exceptions import ReadTimeoutError
from requests.exceptions import ConnectionError as RequestsConnectionError
from instagrapi import Client
from instagrapi.exceptions import LoginRequired, ClientRequestTimeout, MediaNotFound, MediaUnavailable, PleaseWaitFewMinutes, ChallengeRequired
from logger import log
from .exceptions import WrongVaultInstance, FailedCreateDownloaderInstance, FailedAuthInstagram, FailedDownloadPost


class Downloader:
    """
    An Instagram API instance is created by this class and contains a set of all the necessary methods
    to upload content from Instagram to a temporary directory.

    Attributes:
        :attribute configuration (dict): dictionary with configuration parameters for instagram api communication.
        :attribute client (object): instance of the instagram api client.
        :attribute download_methods (dict): dictionary with download methods for instagram api client.
        :attribute general_settings_list (list): list of general session settings for the instagram api.
        :attribute device_settings_list (list): list of device settings for the instagram api.
        :attribute media_type_links (dict): dictionary with media type links for the instagram api client.

    Methods:
        :method _get_login_args: get login arguments for the instagram api.
        :method _create_new_session: create a new session file for the instagram api.
        :method _handle_relogin: handle re-authentication in the instagram api.
        :method _load_session: load or create a session.
        :method _set_session_settings: setting general session settings for the instagram api.
        :method _validate_session_settings: checking the correctness between the session settings and the configuration settings.
        :method exceptions_handler: decorator for handling exceptions in the Downloader class.
        :method login: authentication in instagram api.
        :method get_post_content: getting the content of a post.

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
        ...     'country': 'US',
        ...     'timezone-offset': 10800,
        ...     'proxy-dsn': 'http://localhost:8080'
        ...     'request-timeout': 10,
        ...     'device-settings': {
        ...         'app_version': '269.0.0.18.75', 'version_code': '314665256',
        ...         'manufacturer': 'OnePlus', 'model': '6T Dev', 'device': 'devitron', 'cpu': 'qcom', 'dpi': '480dpi', 'resolution': '1080x1920',
        ...         'android_release': '8.0.0', 'android_version': '26'
        ...     }
        ... }
        >>> vault = Vault()
        >>> downloader = Downloader(configuration, vault)
        >>> status = downloader.get_post_content('shortcode')
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
                :param country (str): country for requests.
                :param timezone-offset (int): timezone offset for requests.
                :param proxy-dsn (str): proxy dsn for requests.
                :param request-timeout (int): request timeout for requests.
                :device-settings (dict): dictionary with device settings for requests.
                    :param app_version (str): application version.
                    :param version_code (str): version code.
                    :param manufacturer (str): manufacturer of the device.
                    :param model (str): model of the device.
                    :param device (str): device name.
                    :param cpu (str): cpu name.
                    :param dpi (str): dpi resolution.
                    :param resolution (str): screen resolution.
                    :param android_release (str): android release version.
                    :param android_version (str): android version.
            :param vault (object): instance of vault for reading configuration downloader-api.
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

        log.info('[Downloader]: creating a new instance...')
        self.client = Client()

        log.info('[Downloader]: setting up the client configuration...')
        self.client.delay_range = [1, int(self.configuration['delay-requests'])]
        self.client.request_timeout = int(self.configuration['request-timeout'])
        self.client.set_proxy(dsn=self.configuration.get('proxy-dsn', None))
        self.general_settings_list = [
            'locale', 'country_code', 'country', 'timezone_offset'
        ]
        self.device_settings_list = [
            'app_version', 'version_code', 'manufacturer', 'model', 'device', 'cpu', 'dpi', 'resolution', 'android_release', 'android_version'
        ]
        self.download_methods = {
            (1, 'any'): self.client.photo_download, (2, 'feed'): self.client.video_download, (2, 'clips'): self.client.clip_download,
            (2, 'igtv'): self.client.igtv_download, (8, 'any'): self.client.album_download
        }
        self.media_type_links = {1: 'p', 8: 'p', 'reel': [2]}

        auth_status = self.login()
        if auth_status == 'logged_in':
            log.info('[Downloader]: instance created successfully with account %s', self.configuration['username'])
        else:
            raise FailedAuthInstagram("Failed to authenticate the Instaloader instance.")

    def _get_login_args(self) -> dict:
        """Get login arguments for the Instagram API"""
        if self.configuration['2fa-enabled']:
            totp_code = self.client.totp_generate_code(seed=self.configuration['2fa-seed'])
            log.info('[Downloader]: 2fa is enabled. TOTP code: %s', totp_code)
            return {
                'username': self.configuration['username'],
                'password': self.configuration['password'],
                'verification_code': totp_code
            }
        return {
            'username': self.configuration['username'],
            'password': self.configuration['password']
        }

    def _create_new_session(self, login_args: dict) -> None:
        """Create a new session file for the Instagram API"""
        self._set_session_settings()
        self.client.login(**login_args)
        self.client.dump_settings(self.configuration['session-file'])
        log.info('[Downloader]: the new session file was created successfully: %s', self.configuration['session-file'])

    def _handle_relogin(self, login_args: dict) -> None:
        """Handle re-authentication in the Instagram API"""
        log.info('[Downloader]: authentication with the clearing of the session...')
        old_uuids = self.client.get_settings().get("uuids", {})
        self.client.set_settings({})
        self.client.set_uuids(old_uuids)
        self._create_new_session(login_args)

    def _load_session(self, login_args: dict) -> None:
        """Load or create a session."""
        log.info('[Downloader]: authentication with the existing session...')
        session_file = self.configuration['session-file']
        if os.path.exists(session_file):
            self.client.load_settings(session_file)
            # Temporarily fix for country, because it is not working in set_settings
            self.client.set_country(country=self.configuration['country'])
            if not self._validate_session_settings():
                self._create_new_session(login_args)
        else:
            self._create_new_session(login_args)

    def _set_session_settings(self) -> None:
        """
        The method for setting general session settings for the Instagram API, such as
            - locale
            - country code
            - country
            - timezone offset
            - device settings
            - user agent
        """
        log.info('[Downloader]: extracting device settings...')
        device_settings = json.loads(self.configuration['device-settings'])
        if not all(item in device_settings.keys() for item in self.device_settings_list):
            raise ValueError("incorrect device settings in the configuration. Please check the configuration in the Vault.")

        # Extract other settings except device settings
        log.info('[Downloader]: extracting other settings...')
        other_settings = {item: None for item in self.general_settings_list}
        for item in other_settings.keys():
            other_settings[item] = self.configuration[item.replace('_', '-')]

        log.debug('[Downloader]: retrieved settings: %s', {**other_settings, 'device_settings': device_settings})

        # Apply all session settings
        self.client.set_settings(settings={**other_settings, 'device_settings': device_settings})
        # Temporarily fix for country
        # Country in set_settings is not working
        self.client.set_country(country=other_settings['country'])
        self.client.set_user_agent()
        log.info('[Downloader]: general session settings have been successfully set: %s', self.client.get_settings())

    def _validate_session_settings(self) -> bool:
        """
        The method for checking the correctness between the session settings and the configuration settings.

        Returns:
            (bool) True if the session settings are equal to the configuration settings, otherwise False.
        """
        log.info('[Downloader]: checking the difference between the session settings and the configuration settings...')
        session_settings = self.client.get_settings()
        for item in self.general_settings_list:
            if str(session_settings[item]) != str(self.configuration[item.replace('_', '-')]):
                log.info(
                    '[Downloader]: the session key value are not equal to the expected value: %s != %s. Session will be reset',
                    session_settings[item], self.configuration[item.replace('_', '-')]
                )
                return False
        device_settings = self.client.get_settings()['device_settings']
        for item in self.device_settings_list:
            if str(device_settings[item]) != str(json.loads(self.configuration['device-settings'])[item]):
                log.info(
                    '[Downloader]: the session key value are not equal to the expected value: %s != %s. Session will be reset',
                    device_settings[item], json.loads(self.configuration['device-settings'])[item]
                )
                return False
        log.info('[Downloader]: the session settings are equal to the expected settings.')
        return True

    @staticmethod
    def exceptions_handler(method) -> None:
        """
        Decorator for handling exceptions in the Downloader class.

        Args:
            :param method (function): method to be wrapped.
        """
        def wrapper(self, *args, **kwargs):
            random_shift = random.randint(600, 7200)
            try:
                return method(self, *args, **kwargs)
            except LoginRequired:
                log.error('[Downloader]: instagram API login required. Re-authenticate after %s minutes', round(random_shift/60))
                time.sleep(random_shift)
                log.info('[Downloader]: re-authenticate after timeout due to login required')
                self.login(method='relogin')
            except ChallengeRequired:
                log.error('[Downloader]: instagram API requires challenge in browser. Retry after %s minutes', round(random_shift/60))
                time.sleep(random_shift)
                log.info('[Downloader]: re-authenticate after timeout due to challenge required')
                self.login()
            except PleaseWaitFewMinutes:
                log.error('[Downloader]: device or IP address has been restricted. Just wait a %s minutes and retry', round(random_shift/60))
                time.sleep(random_shift)
                log.info('[Downloader]: retry after timeout due to restriction')
                self.login(method='relogin')
            except (ReadTimeoutError, RequestsConnectionError, ClientRequestTimeout):
                log.error('[Downloader]: timeout error downloading post content. Retry after 1 minute')
                time.sleep(60)
            return method(self, *args, **kwargs)
        return wrapper

    @exceptions_handler
    def login(self, method: str = 'session') -> str | None:
        """
        The method for authentication in Instagram API.

        Args:
            :param method (str): the type of authentication in the Instagram API. Default: 'session'.
                possible values:
                    'session' - authentication by existing session file or create session file for existing device.
                    'relogin' - authentication as an existing device. Creates a new session file and clears the old attributes.

        Returns:
            (str) logged_in
                or
            None
        """
        log.info('[Downloader]: authentication in the Instagram API with type: %s', method)

        # Generate login arguments
        login_args = self._get_login_args()

        # Handle authentication method
        if method == 'relogin':
            self._handle_relogin(login_args)
        else:
            self._load_session(login_args)

        # Check the status of the authentication
        log.info('[Downloader]: checking the status of the authentication...')
        self.client.get_timeline_feed()
        log.info('[Downloader]: authentication in the Instagram API was successful.')

        return 'logged_in'

    @exceptions_handler
    def get_post_content(self, shortcode: str = None, error_count: int = 0) -> dict | None:
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
            log.error('[Downloader]: the number of errors exceeded the limit: %s', error_count)
            raise FailedDownloadPost("the number of errors exceeded the limit.")

        log.info('[Downloader]: downloading the contents of the post %s...', shortcode)
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
                log.error('[Downloader]: the media type is not supported for download: %s', media_info)
                status = "not_supported"

            if os.listdir(path):
                log.info('[Downloader]: the contents of the post %s have been successfully downloaded', shortcode)
                response = {
                    'post': shortcode,
                    'owner': media_info['user']['username'],
                    'type': media_info['product_type'] if media_info['product_type'] else 'photo',
                    'status': status if status else 'completed'
                }
            else:
                log.error('[Downloader]: temporary directory is empty: %s', path)
                response = {
                    'post': shortcode,
                    'owner': media_info['user']['username'],
                    'type': media_info['product_type'] if media_info['product_type'] else 'photo',
                    'status': status if status else 'failed'
                }

        except (MediaUnavailable, MediaNotFound):
            log.warning('[Downloader]: post %s not found, perhaps it was deleted. Message will be marked as processed', shortcode)
            response = {
                'post': shortcode,
                'owner': 'undefined',
                'type': 'undefined',
                'status': 'source_not_found'
            }

        return response

    @exceptions_handler
    def get_account_info(self, username: str = None) -> dict | None:
        """
        The method for getting information about the account by the specified User ID.

        Args:
            :param username (str): the ID of the user for downloading content.

        Returns:
            (dict) account information
        """
        log.info('[Downloader]: extracting information about the account %s...', username)
        return self.client.user_info_by_username(username=username).dict()

    @exceptions_handler
    def get_account_posts(self, user_id: int = None, cursor: str = None) -> list | None:
        """
        The method for getting the content of a post from a specified User ID.

        Args:
            :param user_id (int): the ID of the user for downloading content.
            :param cursor (str): the cursor for pagination.

        Returns:
            (list) list of posts
        """
        log.info('[Downloader]: extracting the list of posts for the user pk %s...', user_id)
        return self.client.user_medias_paginated(user_id=user_id, amount=20, end_cursor=cursor)
