"""This module processes the content uploaded from Instagram
and uploads the found media files (image, video) to the dropbox cloud.
"""
import os
import dropbox
from logger import log


class DropboxAPI:
    """This class creates an instance with a connection to the dropbox api
    and uploads all the media content of the local directory to the dropbox cloud.
    """
    def __init__(self,
                 dropbox_token: str = None,
                 max_connections: int = 3,
                 max_retries_on_error: int = 3,
                 timeout: int = 60
    ) -> None:
        """A function for create a new dropbox api client instance.
        :param dropbox_token: Token for authenticated in dropbox api.
        :type dropbox_token: str
        :default dropbox_token: None
            more: https://developers.dropbox.com/ru-ru/oauth-guide
        :param max_connections: Maximum number of connections at the same time.
        :type max_connections: int
        :default max_connections: 3
        :param max_retries_on_error: Maximum number of retries when request fail.
        :type max_retries_on_error: int
        :default max_retries_on_error: 3
        :param timeout: Maximum waiting time for request completion.
        :type timeout: int
        :default timeout: 60
        """
        self.homepath = os.getcwd()
        try:
            dropbox_session = dropbox.create_session(
                max_connections=max_connections,
                proxies=None
            )
            self.dropbox_client = dropbox.Dropbox(
                dropbox_token,
                max_retries_on_error=max_retries_on_error,
                max_retries_on_rate_limit=None,
                user_agent=None,
                session=dropbox_session,
                headers=None,
                timeout=timeout
            )
        except dropbox.exceptions.DropboxException as dropboxexception:
            log.error(
                '[class.%s] creating dropbox instance faild: %s',
                __class__.__name__,
                dropboxexception
            )


    def upload_file(
        self,
        soruce_file: str = None,
        dropbox_dir: str = None
    ) -> str:
        """A function for uploading the contents of the target directory
        to the dropbox cloud directory.
        :param soruce_file: The path to the local file with the contents.
        :type soruce_file: str
        :default soruce_file: None
        :param dropbox_dir: The name of the traget directory in the dropbox cloud.
        :type dropbox_dir: str
        :default dropbox_dir: None
        """
        log.info(
            '[class.%s] starting upload files from %s',
            __class__.__name__,
            soruce_file
        )
        with open(soruce_file, 'rb') as file_transfer:
            try:
                response = self.dropbox_client.files_upload(
                    file_transfer.read(),
                    f"/{dropbox_dir}/{soruce_file.split('/')[-1]}",
                    autorename=True
                )
                log.info(
                    '[class.%s] %s has been uploaded',
                    __class__.__name__,
                    response.name
                )
            except dropbox.exceptions.DropboxExceptiontion as dropboxexception:
                log.error(
                    '[class.%s] uploading file to dropbox api faild: %s',
                    __class__.__name__,
                    dropboxexception
                )
                return "faild"
        file_transfer.close()

        log.info(
            '[class.%s] %s successful transfering %s bytes',
            __class__.__name__,
            response.id,
            response.size
        )
        return "success"
