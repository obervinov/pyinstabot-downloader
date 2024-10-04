# pylint: disable=R0801
"""
This module processes the content uploaded from Instagram
and uploads the found media files (image, video) to the destination storage.
"""
import os
from typing import Union
import dropbox
from mega import Mega
from webdav3.client import Client as WebDavClient
from logger import log
from .exceptions import WrongVaultInstance, FailedInitUploaderInstance, WrongStorageType


class Uploader:
    """
    This class creates an instance with a connection
    to the target storage for uploading media content.
    """
    def __init__(
        self,
        configuration: dict = None,
        vault: object = None
    ) -> None:
        """
        The method creates an instance with a connection to the target storage for uploading media content.

        Args:
            :param configuration (dict): dictionary with target storage parameters.
                :param username (str): username for authentication in the target storage.
                :param password (str): password for authentication in the target storage.
                :param storage-type (str): type of storage for uploading content. Can be: 'dropbox', 'mega' or 'webdav'.
                :param exclude-types (str): exclude files with this type from uploading. Example: '.json, .txt'.
                :param source-directory (str): the path to the local directory with media content for uploading.
                :param destination-directory (str): a subdirectory in the cloud storage where the content will be uploaded.
            :param vault (object): instance of vault for reading authorization data.

        Returns:
            None

        Examples:
            >>> configuration = {
            ...     'username': 'my_username',
            ...     'password': 'my_password',
            ...     'storage-type': 'webdav',
            ...     'url': 'https://webdav.example.com/directory',
            ...     'exclude-types': '.json, .txt',
            ...     'source-directory': '/path/to/source/directory',
            ...     'destination-directory': '/path/to/destination/directory'
            ... }
            >>> vault = Vault()
            >>> uploader = Uploader(configuration, vault)
        """
        if not vault:
            raise WrongVaultInstance("Wrong vault instance, you must pass the vault instance to the class argument.")

        if configuration:
            self.configuration = configuration
        elif not configuration:
            self.configuration = vault.kv2engine.read_secret(path='configuration/uploader-api')
        else:
            raise FailedInitUploaderInstance(
                "Failed to initialize the Uploader instance."
                "Please check the configuration in class argument or the secret with the configuration in the Vault."
            )

        self.local_directory = f"{os.getcwd()}/{self.configuration['source-directory']}"
        self.storage = self._init_storage_connection()
        self._check_incomplete_transfers()

    def _init_storage_connection(self) -> object:
        """
        The method for initializing a connection to the target storage.
        Can be: 'dropbox', 'mega' or 'webdav'.

        Args:
            None

        Returns:
            (object) connection object to the target storage.
        """
        if self.configuration['storage-type'] == 'dropbox':
            return dropbox.Dropbox(oauth2_access_token=self.configuration['password'])

        if self.configuration['storage-type'] == 'mega':
            mega = Mega()
            return mega.login(email=self.configuration['username'], password=self.configuration['password'])

        if self.configuration['storage-type'] == 'webdav':
            options = {
                'webdav_hostname': self.configuration['url'],
                'webdav_login': self.configuration['username'],
                'webdav_password': self.configuration['password']
            }
            return WebDavClient(options)

        raise WrongStorageType("Wrong storage type, please check the configuration. 'storage-type' can be: 'dropbox', 'mega' or 'webdav'.")

    def _check_incomplete_transfers(self) -> None:
        """
        The method for checking uploads in temp directory that for some reason could not be uploaded to the target cloud storage.

        Args:
            None

        Returns:
            None
        """
        log.info('[Uploader]: Checking incomplete transfers...')
        for root, dirs, _ in os.walk(self.configuration['source-directory']):
            for dir_name in dirs:
                sub_directory = os.path.join(root, dir_name)
                # Check the subdirectory for files
                sub_files = [f for f in os.listdir(sub_directory) if os.path.isfile(os.path.join(sub_directory, f))]
                if sub_files:
                    log.warning('[Uploader]: An unloaded artifact was found: %s', sub_directory)
                    self.run_transfers(sub_directory=sub_directory)
                else:
                    log.info('[Uploader]: Remove of an empty directory %s', sub_directory)
                    os.rmdir(sub_directory)

    def run_transfers(
        self,
        sub_directory: str = None
    ) -> str:
        """
        External entrypoint method for uploading media files to the target cloud storage.

        Args:
            :param sub_directory (str): the name of the subdirectory in the source directory with media content.

        Returns:
            (str) 'completed'
                (this means that the file has been successfully uploaded to the cloud)
            (str) 'not_completed'
                (this means that an error has occurred the file is not uploaded to the cloud)
        """
        transfers = {}
        result = ""
        log.info('[Uploader]: Preparing media files for transfer to the %s...', self.configuration['storage-type'])
        for root, _, files in os.walk(f"{self.configuration['source-directory']}{sub_directory}"):
            for file in files:
                if file.split('.')[-1] in self.configuration.get('exclude-types', None):
                    os.remove(os.path.join(root, file))
                else:
                    transfers[file] = self.upload_to_cloud(
                        source=os.path.join(root, file),
                        destination=root.split('/')[1]
                    )
                    if transfers[file] == 'uploaded':
                        os.remove(os.path.join(root, file))
                        result = 'completed'
                    else:
                        result = 'not_completed'
        log.info('[Uploader]: List of all transfers %s', transfers)
        return result

    def upload_to_cloud(
        self,
        source: str = None,
        destination: str = None
    ) -> Union[str, None]:
        """
        The method of uploading the contents of the source directory to the target cloud storage.

        Args:
            :param source (str): the path to the local file to transfer to the target storage.
            :param destination (str): the name of the target directory in the destination storage.

        Returns:
            (str) 'uploaded'
                or
            None
        """
        log.info('[Uploader]: Starting upload file %s to %s://%s', source, self.configuration['storage-type'], destination)
        response = None
        result = None

        if self.configuration['storage-type'] == 'mega':
            directory = f"{self.configuration['destination-directory']}/{destination}"
            log.info('[Uploader]: Trying found mega folder %s...', directory)
            mega_folder = self.storage.find(directory, exclude_deleted=True)
            if not mega_folder:
                self.storage.create_folder(directory)
                mega_folder = self.storage.find(directory, exclude_deleted=True)
                log.info('[Uploader]: Mega folder not found, created new folder %s', mega_folder)
            else:
                log.info('[Uploader]: Mega folder %s was found', mega_folder)
            response = self.storage.upload(filename=source, dest=mega_folder[0])
            result = "uploaded"

        if self.configuration['storage-type'] == 'dropbox':
            with open(source, 'rb') as file_transfer:
                response = self.storage.files_upload(file_transfer.read(), f"/{destination}/{source.split('/')[-1]}")
            file_transfer.close()
            result = "uploaded"

        if self.configuration['storage-type'] == 'webdav':
            if not self.storage.check(f"{self.configuration['destination-directory']}/{destination}"):
                self.storage.mkdir(f"{self.configuration['destination-directory']}/{destination}")
            self.storage.upload_sync(
                remote_path=f"{self.configuration['destination-directory']}/{destination}/{source.split('/')[-1]}",
                local_path=source
            )
            response = self.storage.info(f"{self.configuration['destination-directory']}/{destination}/{source.split('/')[-1]}")['etag']
            result = "uploaded"

        log.info('[Uploader]: %s successful transferred', response)
        return result
