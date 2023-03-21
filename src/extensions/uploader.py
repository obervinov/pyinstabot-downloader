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
        self.storage = storage
        self.auth = auth
        self.settings = settings
        self.homepath = os.getcwd()
        self.vault_client = kwargs.get('vault_client')
        log.info(
            '[class.%s] uploader instance init with %s storage type',
            __class__.__name__,
            storage
        )
        if self.storage == 'dropbox':
            # more: https://developers.dropbox.com/ru-ru/oauth-guide
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


    def prepare_content(
        self,
        dirname: str = None
    ) -> dict:
        """
        Method of preparing media files for transfer to the target storage (cloud or local).
        :param dirname: Name of the directory for receiving media files.
        :type dirname: str
        :default dirname: None
        """
        log.info(
            '[class.%s] preparing media files for transfer to the target storage -> %s ',
            __class__.__name__,
            self.storage
        )
        transfers = {}
        for root, _, files in os.walk(f"{self.homepath}/{dirname}"):
            for file in files:
                if ".txt" in file:
                    os.remove(os.path.join(root, file))
                else:
                    transfers[file] = self.upload_file()
                    if transfers[file] == 'uploaded':
                        os.remove(os.path.join(root, file))
        if len(os.listdir(f"{self.homepath}/{dirname}")) == 0:
            os.rmdir(f"{self.homepath}/{dirname}")


    def upload_file(
        self,
        source: str = None,
        destination: str = None
    ) -> str:
        """
        The method of uploading the contents of the target directory
        to the cloud or local directory.
        
        :param source: The path to the local file to transfer to the target storage.
        :type source: str
        :default source: None
        :param destination: The name of the target directory in the destination storage.
        :type destination: str
        :default destination: None
        """
        log.info(
            '[class.%s] starting upload file %s to %s:%s',
            __class__.__name__,
            source,
            self.storage,
            destination
        )
        if self.storage == 'dropbox':
            # more https://www.dropbox.com/developers/documentation/python
            with open(source, 'rb') as file_transfer:
                try:
                    response = self.dropbox_client.files_upload(
                        file_transfer.read(),
                        f"/{destination}/{source.split('/')[-1]}"
                    )
                    log.info(
                        '[class.%s] %s has been uploaded to %s',
                        __class__.__name__,
                        response.name,
                        self.storage
                    )
                except dropbox.exceptions.DropboxException as dropboxexception:
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
