# pylint: disable=duplicate-code
"""
This module interacts with the instagram api and uploads content to a temporary directory.
Supports downloading the content of the post by link and getting information about the account.
https://github.com/subzeroid/instagrapi
"""
import os
import time
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

    Methods:
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
        ...         'app_metadata': {'app_version': '269.0.0.18.75', 'version_code': '314665256'},
        ...         'device_metadata': {'manufacturer': 'OnePlus', 'model': '6T Dev', 'device': 'devitron', 'cpu': 'qcom', 'dpi': '480dpi', 'resolution': '1080x1920'},
        ...         'os_metadata': {'android_release': '8.0.0', 'android_version': '26'}
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
                    :param app_metadata (dict): dictionary with app metadata for requests. Must be: 'app_version', 'version_code'.
                    :param os_metadata (dict): dictionary with os metadata for requests. Must be: 'android_version', 'android_release'.
                    :param device_metadata (dict): dictionary with device metadata for requests. Must be: 'manufacturer', 'model', 'device', 'cpu', 'dpi', 'resolution'.
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

        log.info('[Downloader]: Creating a new instance...')
        self.client = Client()

        log.info('[Downloader]: Setting up the client configuration...')
        self.client.delay_range = [1, int(self.configuration['delay-requests'])]
        self.client.request_timeout = int(self.configuration['request-timeout'])
        self.client.set_proxy(dsn=self.configuration.get('proxy-dsn', None))
        self.general_settings_list = ['locale', 'country_code', 'country', 'timezone_offset']
        self.device_settings_list = ['app_metadata', 'os_metadata', 'device_metadata']
        self.download_methods = {
            (1, 'any'): self.client.photo_download,
            (2, 'feed'): self.client.video_download,
            (2, 'clips'): self.client.clip_download,
            (2, 'igtv'): self.client.igtv_download,
            (8, 'any'): self.client.album_download
        }

        auth_status = self.login()
        if auth_status == 'logged_in':
            log.info('[Downloader]: Instance created successfully with account %s', self.configuration['username'])
        else:
            raise FailedAuthInstagram("Failed to authenticate the Instaloader instance.")

    def _set_session_settings(self) -> None:
        """
        The method for setting general session settings for the Instagram API, such as
            - locale
            - country code
            - timezone offset
            - device settings
            - user agent
        """
        log.info('[Downloader]: Extracting device settings...')
        device_settings = self.configuration['device-settings']
        if not all(item in device_settings.keys() for item in self.device_settings_list):
            raise ValueError(
                "Incorrect app, os or device metadata format. Must be: "
                "os_metadata: 'android_version', 'android_release', "
                "app_metadata: 'app_version', 'version_code', "
                "device_metadata: 'manufacturer', 'model', 'device', 'cpu', 'dpi', 'resolution'."
            )
        device_settings = {
            'app_version': device_settings['app_metadata']['app_version'],
            'version_code': device_settings['app_metadata']['version_code'],
            'android_version': device_settings['os_metadata']['android_version'],
            'android_release': device_settings['os_metadata']['android_release'],
            'dpi': device_settings['device_metadata']['dpi'],
            'resolution': device_settings['device_metadata']['resolution'],
            'manufacturer': device_settings['device_metadata']['manufacturer'],
            'model': device_settings['device_metadata']['model'],
            'device': device_settings['device_metadata']['device'],
            'cpu': device_settings['device_metadata']['cpu']
        }

        log.info('[Downloader]: Extracting other settings...')
        # Extract other settings except device settings
        other_settings = {item: None for item in self.general_settings_list}
        for item in other_settings.keys():
            other_settings[item] = self.configuration[item.replace('_', '-')]

        # Apply all session settings
        self.client.set_settings({**other_settings, 'device_settings': device_settings})
        self.client.set_user_agent()
        log.info('[Downloader]: General session settings have been successfully set: %s', self.client.get_settings())

    def _validate_session_settings(self) -> bool:
        """
        The method for checking the correctness between the session settings and the configuration settings.

        Returns:
            (bool) True if the session settings are equal to the configuration settings, otherwise False.
        """
        log.info('[Downloader]: Checking the difference between the session settings and the configuration settings...')
        session_settings = self.client.get_settings()
        for item in self.general_settings_list:
            if session_settings[item] != self.configuration[item.replace('_', '-')]:
                log.info('[Downloader]: The session settings are not equal to the configuration settings and could be reset.')
                return False
        log.info('[Downloader]: The session settings are equal to the configuration settings.')
        return True

    @staticmethod
    def exceptions_handler(method) -> None:
        """
        Decorator for handling exceptions in the Downloader class.

        Args:
            :param method (function): method to be wrapped.
        """
        def wrapper(self, *args, **kwargs):
            try:
                return method(self, *args, **kwargs)
            except LoginRequired:
                log.error('[Downloader]: Instagram API login required. Re-authentication...')
                self.login(method='relogin')
            except ChallengeRequired:
                log.error('[Downloader]: Instagram API requires challenge. Need manually pass in browser. Retry after 1 hour')
                time.sleep(3600)
                self.login()
            except PleaseWaitFewMinutes:
                log.error('[Downloader]: Device or IP address has been restricted. Just wait a one hour and try again')
                time.sleep(3600)
                self.login(method='relogin')
            except (ReadTimeoutError, RequestsConnectionError, ClientRequestTimeout):
                log.error('[Downloader]: Timeout error downloading post content. Retry after 1 minute')
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
                    'session' - authentication by existing session file. Or create session file for existing device.
                    'relogin' - authentication as an existing device. This will create a new session file and clear the old attributes.

        Returns:
            (str) logged_in
                or
            None
        """
        log.info('[Downloader]: Authentication in the Instagram API with type: %s', method)

        # 2FA authentication settings
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

        # Login to the Instagram API
        create_new_session = False
        if method == 'relogin':
            log.info('[Downloader]: Authentication with the clearing of the session...')
            # extract old uuids and clear settings
            old_uuids = self.client.get_settings()["uuids"]
            self.client.set_settings({})
            # set old uuids and set general session settings
            self.client.set_uuids(old_uuids)
            create_new_session = True
        else:
            log.info('[Downloader]: Authentication with the existing session...')
            if os.path.exists(self.configuration['session-file']):
                self.client.load_settings(self.configuration['session-file'])
                if not self._validate_session_settings():
                    create_new_session = True
            else:
                create_new_session = True

        self._set_session_settings()
        self.client.login(**login_args)

        if create_new_session:
            self.client.dump_settings(self.configuration['session-file'])
            log.info('[Downloader]: The session file was created successfully: %s', self.configuration['session-file'])

        # Check the status of the authentication
        log.info('[Downloader]: Checking the status of the authentication...')
        self.client.get_timeline_feed()
        log.info('[Downloader]: Authentication in the Instagram API was successful.')

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

        except (MediaUnavailable, MediaNotFound):
            log.warning('[Downloader]: Post %s not found, perhaps it was deleted. Message will be marked as processed', shortcode)
            response = {
                'post': shortcode,
                'owner': 'undefined',
                'type': 'undefined',
                'status': 'source_not_found'
            }

        return response
