"""
This module processes the content uploaded from Instagram
and uploads the found media files (image, video) to the destination storage.
"""
import os
import dropbox
from logger import log


class Uploader:
    """
    This class creates an instance with a connection
    to the target storage for uploading local media content.
    """
    def __init__(
        self,
        storage: str = 'local'|'dropbox'|'meganz',
        auth: dict = None,
        settings: dict = None,
        **kwargs
    ) -> None:
        """
        A Method creates an instance with a connection
        to the target storage for uploading local media content.

        :param storage: Dictionary with authorization parameters.
        :type storage: str
        :default storage: 'local'|'dropbox'|'meganz'
        :param auth: Dictionary with authorization parameters.
            {'username': None, 'password': None} or {'token': None}
        :type auth: dict
        :default auth: None
        :param settings: Dictionary with settings parameters.
            {'max_connections': None, 'timeout': None}
        :type settings: dict
        :default settings: None
        :param **kwargs: Passing additional parameters for uploader.
        :type **kwargs: dict
        :param kwargs.vault_client: Instance of vault_client for reading authorization data.
        :type kwargs.vault_client: object
        :default kwargs.vault_client: None
        """
        self.storafe = storage
        self.auth = auth
        self.settings = settings
        self.homepath = os.getcwd()
        self.vault_client = kwargs.get('vault_client')

        if storage == 'dropbox':
            token = self.vault_client.vault_read_secrets('configuration/dropbox', 'token')
            try:
                dropbox_session = dropbox.create_session(
                    max_connections=3,
                    proxies=None
                )
                self.dropbox_client = dropbox.Dropbox(
                    oauth2_access_token=token,
                    max_retries_on_error=3,
                    max_retries_on_rate_limit=None,
                    user_agent=None,
                    session=dropbox_session,
                    headers=None,
                    timeout=60
                )
            except dropbox.exceptions.DropboxException as dropboxexception:
                log.error(
                    '[class.%s] creating dropbox instance faild: %s',
                    __class__.__name__,
                    dropboxexception
                )


    def upload_dropbox(
        self,
        soruce_file: str = None,
        dropbox_dir: str = None
    ) -> str:
        """
        A Method for uploading the contents of the target directory
        to the dropbox cloud directory.
        https://www.dropbox.com/developers/documentation/python
        
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
