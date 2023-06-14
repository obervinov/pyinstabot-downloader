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
        storage: dict = {
            'type': 'local'|'dropbox',
            'temporary': None
        } | None,
        **kwargs
    ) -> None:
        """
        A Method creates an instance with a connection
        to the target storage for uploading local media content.

        :param auth: Dictionary with authorization parameters.
        :type auth: dict
        :default auth: {'token': None} | {'username': None, 'password': None} | None
        :param storage: Dictionary with storage parameters.
        :type storage: dict
        :default storage: {'type': 'local'|'dropbox', 'temporary': None} | None
            :param storage.type: Type of storage for uploading content.
            :type storage.type: str
            :default storage.type: 'local'|'dropbox'
            :param storage.temporary: Type of storage for uploading content.
            :type storage.temporary: str
            :default storage.temporary: None
        :param **kwargs: Passing additional parameters for uploader.
        :type **kwargs: dict
            :param kwargs.vault_client: Instance of vault_client for reading authorization data.
            :type kwargs.vault_client: object
            :default kwargs.vault_client: None
        """
        self.storage = storage
        self.temporary_dir = f"{os.getcwd()}/{self.storage['temporary']}"
        self.vault_client = kwargs.get('vault_client')
        log.info(
            '[class.%s] uploader instance init with %s storage type',
            __class__.__name__,
            storage['type']
        )
        if self.storage['type'] == 'dropbox':
            token = self.vault_client.vault_read_secrets('configuration/dropbox', 'token')
            try:
                dropbox_session = dropbox.create_session(
                    max_connections=3
                )
                self.dropbox_client = dropbox.Dropbox(
                    oauth2_access_token=token,
                    session=dropbox_session,
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
        return
        'uploaded'   - this means that the file has been successfully uploaded to the cloud
        'None'       - this means that an error has occurred the file is not uploaded to the cloud
        'save_local' - this means that the file must remain in the local (temporary directory)
                       and it is not required to perform any actions with it
        {
            '/root/path/shortcode/file1.jpeg': 'uploaded',
            '/root/path/shortcode/file2.jpeg': None
        }
        or
        {
            '/root/path/shortcode/file1.jpeg': 'save_local',
            '/root/path/shortcode/file2.jpeg': 'save_local'
        }
        """
        log.info(
            '[class.%s] preparing media files for transfer to the target storage -> %s ',
            __class__.__name__,
            self.storage
        )
        transfers = {}
        for root, _, files in os.walk(f'{self.temporary_dir}{dirname}'):
            for file in files:
                if ".txt" in file:
                    os.remove(os.path.join(root, file))
                else:
                    transfers[file] = self.upload_file(
                        os.path.join(root, file),
                        dirname
                    )
                    if transfers[file] == 'uploaded':
                        os.remove(
                            os.path.join(root, file)
                        )
        if len(os.listdir(f'{self.temporary_dir}{dirname}')) == 0:
            os.rmdir(f'{self.temporary_dir}{dirname}')
        return transfers


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
            '[class.%s] starting upload file %s to %s//:%s',
            __class__.__name__,
            source,
            self.storage['type'],
            destination
        )

        if self.storage['type'] == "local":
            return "save_local"

        if self.storage['type'] == 'dropbox':
            with open(source, 'rb') as file_transfer:
                try:
                    response = self.dropbox_client.files_upload(
                        file_transfer.read(),
                        f'/{destination}/{source.split("/")[-1]}'
                    )
                    log.info(
                        '[class.%s] %s successful transfering',
                        __class__.__name__,
                        response.name
                    )
                    return "uploaded"
                except dropbox.exceptions.DropboxException as dropboxexception:
                    log.error(
                        '[class.%s] error when uploading a file via the dropbox api: %s',
                        __class__.__name__,
                        dropboxexception
                    )
            file_transfer.close()
        return None
