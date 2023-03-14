"""
This module interacts with the instagram api.
Supports downloading the content of the post by link,
the entire content of posts in the account
and getting account about.
https://instaloader.github.io/module/instaloader.html
"""
import os
import instaloader
from logger import log


class InstagramAPI:
    """
    This class creates an instance with a connection to the instagram api.
    Supports downloading the content of the post by link,
    the entire content of posts in the account
    and getting account about.
    """

    def __init__(
        self,
        username: str = None,
        password: str = None,
        sessionfile: str = None,
        savepath: str = 'tmp/',
        useragent: str = None,
        maxretry: int = 3,
        timeout: float = 300.0
    ) -> None:
        """
        Function for create a new instagram api client instance.
        
        :param user: Username for authentication in the instagram api.
        :type user: str
        :default user: None
        :param password: Password for authentication in the instagram api.
        :type password: str
        :default password: None
        :param sessionfile: The path to the session file from the instagram session.
        :type sessionfile: str
        :default sessionfile: None
        :param savepath: Local directory for saving downloaded content.
        :type savepath: str
        :default savepath: tmp/
        :param useragent: User-Agent header.
        :type useragent: str
        :default useragent: None
        :param maxretry: The maximum number of attempts to reconnect to the api in case of failure.
        :type maxretry: int
        :default maxretry: 3
        :param timeout: Maximum waiting time for a response from the api.
        :type timeout: float
        :default timeout: 300.0
        """
        self.username = username
        self.password = password
        self.sessionfile = sessionfile
        self.savepath = savepath
        self.useragent = useragent
        self.maxretry = maxretry
        self.timeout = timeout

        self.instaloader_client = instaloader.Instaloader(
            sleep=True,
            quiet=True,
            user_agent=self.useragent,
            dirname_pattern=f"{self.savepath}/{{profile}}_{{shortcode}}",
            filename_pattern='{profile}_{shortcode}_{filename}',
            download_pictures=True,
            download_videos=True,
            download_video_thumbnails=True,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=True,
            post_metadata_txt_pattern=None,
            storyitem_metadata_txt_pattern=None,
            max_connection_attempts=self.maxretry,
            request_timeout=self.timeout,
            rate_controller=None,
            resume_prefix='iterator',
            check_resume_bbd=True,
            slide=None,
            iphone_support=True
        )
        try:
            if os.path.exists(self.sessionfile):
                self.instaloader_client.load_session_from_file(
                    self.username,
                    self.sessionfile
                )
                log.info(
                    '[class.%s] session file was load success',
                    __class__.__name__
                )
            else:
                self.instaloader_client.login(
                    self.username,
                    self.password
                )
                log.info(
                    '[class.%s] login with credentials was successful',
                    __class__.__name__
                )
                self.instaloader_client.save_session_to_file(self.sessionfile)
                log.info(
                    '[class.%s] new session file %s was save success',
                    __class__.__name__,
                    self.sessionfile
                )    

        except instaloader.exceptions.LoginRequiredException as loginrequiredexception:
            log.warning(
                '[class.%s] login required: %s',
                __class__.__name__,
                loginrequiredexception
            )
            log.info(
                '[class.%s] trying login with username/password...',
                __class__.__name__
                )
            try:
                self.instaloader_client.login(
                    self.username,
                    self.password
                )
                self.instaloader_client.save_session_to_file(sessionfile)
                log.info(
                    '[class.%s] new session file %s was save success',
                    __class__.__name__,
                    sessionfile
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
        Function for getting a list posts of instagram account posts.
        
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
    ) -> str:
        """
        Function for getting the content of a post from an instagram account.
        
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
            return "success", post.owner_username
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
        return 'faild'
