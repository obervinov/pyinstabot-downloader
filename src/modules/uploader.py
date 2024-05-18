# pylint: disable=R0801
"""
This module processes the content uploaded from Instagram
and uploads the found media files (image, video) to the destination storage.
"""
import os
from typing import Union
import dropbox
from mega import Mega
from logger import log
from .exceptions import WrongVaultInstance, FailedInitUploaderInstance, WrongStorageType


class Uploader:
    """
    This class creates an instance with a connection
    to the target storage for uploading local media content.
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
                :param storage-type (str): type of storage for uploading content. Can be: 'dropbox', 'mega'.
                :param enabled (bool): enable or disable the uploader instance.
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
            ...     'storage-type': 'dropbox',
            ...     'enabled': True,
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
            self.configuration = vault.read_secret(path='configuration/uploader-api')
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

        raise WrongStorageType("Wrong storage type, please check the configuration. It can be 'dropbox' or 'mega'.")

    def _check_incomplete_transfers(self) -> None:
        """
        The method for checking uploads in temp storage that for some reason could not be uploaded to the cloud.

        Args:
            None

        Returns:
            None
        """
        log.info('[class.%s] checking incomplete transfers in the temporary directory...', __class__.__name__)
        for root, dirs, _ in os.walk(self.configuration['source-directory']):
            for dir_name in dirs:
                sub_directory = os.path.join(root, dir_name)
                # Check if the sub-directory contains files
                sub_files = [f for f in os.listdir(sub_directory) if os.path.isfile(os.path.join(sub_directory, f))]
                if sub_files:
                    log.warning('[class.%s] an unloaded artifact was found: %s', __class__.__name__, sub_directory)
                    self.run_transfers(sub_directory=sub_directory)
                else:
                    log.info('[class.%s] remove of an empty directory %s', __class__.__name__, sub_directory)
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
        log.info('[class.%s] preparing media files for transfer to the %s cloud...', __class__.__name__, self.configuration['storage-type'])
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
        log.info('[class.%s] All transfers list: %s', __class__.__name__, transfers)
        return result

    def upload_to_cloud(
        self,
        source: str = None,
        destination: str = None
    ) -> Union[str, None]:
        """
        The method of uploading the contents of the source directory to the cloud storage.

        Args:
            :param source (str): the path to the local file to transfer to the target storage.
            :param destination (str): the name of the target directory in the destination storage.

        Returns:
            (str) 'uploaded'
                or
            None
        """
        log.info('[class.%s] starting upload file %s to %s://%s', __class__.__name__, source, self.configuration['storage-type'], destination)
        response = None
        result = None

        if self.configuration['storage-type'] == 'mega':
            directory = f"{self.configuration['destination-directory']}/{destination}"
            log.info('[class.%s] trying found mega folder %s...', __class__.__name__, directory)
            mega_folder = self.storage.find(directory, exclude_deleted=True)
            if not mega_folder:
                self.storage.create_folder(directory)
                mega_folder = self.storage.find(directory, exclude_deleted=True)
                log.info('[class.%s] mega folder not found, created new folder %s', __class__.__name__, mega_folder)
            log.info('[class.%s] mega folder %s was found', __class__.__name__, mega_folder)
            response = self.storage.upload(filename=source, dest=mega_folder[0])
            result = "uploaded"

        if self.configuration['storage-type'] == 'dropbox':
            with open(source, 'rb') as file_transfer:
                response = self.storage.files_upload(file_transfer.read(), f"/{destination}/{source.split('/')[-1]}")
            file_transfer.close()
            result = "uploaded"

        log.info('[class.%s] %s successful transferred', __class__.__name__, response)
        return result
