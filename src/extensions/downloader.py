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
        auth: dict = {
            'username': None,
            'password': None,
            'sessionfile': None
        } | None,
        settings: dict = {
            'savepath': None,
            'useragent': None
        } | None,
        **kwargs
    ) -> None:
        """
        Method for create a new instagram api client instance.
        
        :param auth: Dictionary with authorization parameters.
        :type auth: dict
        :default auth: {'username': None, 'password': None, 'sessionfile': None} | None                
        :param auth.username: Username for authentication in the instagram api.
        :type auth.username: str
        :default auth.username: None
        :param auth.password: Password for authentication in the instagram api.
        :type auth.password: str
        :default auth.password: None
        :param auth.sessionfile: The path to the session file from the instagram session.
        :type auth.sessionfile: str
        :default auth.sessionfile: None
        :param settings: Dictionary with settings instaloader parameters.
        :type settings: dict
        :default settings: {'savepath': None', 'useragent': None} | None
        :param settings.savepath: Local directory for saving downloaded content.
        :type settings.savepath: str
        :default settings.savepath: None
        :param settings.useragent: User-Agent header.
        :type settings.useragent: str
        :default settings.useragent: None
        :param **kwargs: Passing additional parameters for downloader.
        :type **kwargs: dict
        :param kwargs.vault_client: Instance of vault for recording or reading download history.
        :type kwargs.vault_client: object
        :default kwargs.vault_client: None
        """
        self.auth = auth
        self.settings = settings
        self.vault_client = kwargs.get('vault_client')

        # If the authorization data is not defined, read their values from the vault
        if (not self.auth['username']) or (self.auth['password']):
            self.auth['username'] = self.vault_client.vault_read_secrets(
                'configuration/instagram', 'username'
            )
            self.auth['password'] = self.vault_client.vault_read_secrets(
                'configuration/instagram', 'password'
            )

        self.instaloader_client = instaloader.Instaloader(
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
                self.instaloader_client.load_session_from_file(
                    self.auth['username'],
                    self.auth['sessionfile']
                )
                log.info(
                    '[class.%s] session file was load success',
                    __class__.__name__
                )
            else:
                self.instaloader_client.login(
                    self.auth['username'],
                    self.auth['password']
                )
                log.info(
                    '[class.%s] login with credentials was successful',
                    __class__.__name__
                )
                self.instaloader_client.save_session_to_file(self.auth['sessionfile'])
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
                self.instaloader_client.login(
                    self.auth['username'],
                    self.auth['password']
                )
                self.instaloader_client.save_session_to_file(self.auth['sessionfile'])
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
    ) -> list:
        """
        Method for getting a list posts of instagram account.
        
        :param username: Instagram username to get a list of posts.
        :type username: str
        :default username: None
        """
        try:
            profile = instaloader.Profile.from_username(
                self.instaloader_client.context,
                username
            )
            log.info(
                '[class.%s] the %s profile was readed success',
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
    ) -> None:
        """
        Method for getting the content of a post from a specified Instagram account.
        
        :param shortcode: The shortcode is the ID of the record for downloading content.
        :type shortcode: str
        :default shortcode: None
        """
        try:
            post = instaloader.Post.from_shortcode(
                self.instaloader_client.context,
                shortcode
            )
            self.instaloader_client.download_post(post, '')
            log.info(
                '[class.%s] the contents of the %s have been successfully downloaded '
                'to the temporary storage',
                __class__.__name__,
                shortcode
            )
            self.vault_client.vault_put_secrets(
                f'history/{post.owner_username}',
                shortcode,
                "downloaded"
            )
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


    def get_download_info(
        self,
        account_name: str = None
    ) -> dict:
        """
        Method for collecting all the necessary information
        to download all posts from the specified account.
        Checks the history of already uploaded posts
        and provides information for cyclic downloading.
        
        :param account_name: Instagram account name to check the uploaded history.
        :type account_name: str
        :default account_name: None
        """
        try:
            log.info(
                '[class.%s] excluding shortcodes that are already dowloaded...',
                __class__.__name__
            )
            # List of shortcodes received from instagram
            account_shortcodes = self.get_posts()
            # A list of shortcodes that have not been downloaded yet and will need to be downloaded again
            fresh_shortcodes = []
            # A list of shortcodes that have already been previously uploaded and their history is saved
            history_shortcodes = self.vault_client.vault_read_secrets(
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
                "shortcodes_count": len(account_shortcodes),
                "shortcodes_exist": len(history_shortcodes)
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
