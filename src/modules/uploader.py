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
            configuration = vault.read_secret(path='configuration/uploader-api')
        else:
            raise FailedInitUploaderInstance(
                "Failed to initialize the Uploader instance."
                "Please check the configuration in class argument or the secret with the configuration in the Vault."
            )

        if configuration.get('enabled', False):
            self.local_directory = f"{os.getcwd()}/{self.configuration['source-directory']}"
            self.storage = self._init_storage_connection()
            self._check_incomplete_transfers()
        else:
            self.storage = None
            log.warning('[class.%s] uploader instance is disabled', __class__.__name__)

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
        for _, artifacts, _ in os.walk(self.configuration['source-directory']):
            for artifact in artifacts:
                log.warning('[class.%s] an unloaded artifact was found %s', __class__.__name__, artifact)
                self.upload_content(os.path.join(artifact))

    def upload_content(
        self,
        sub_directory: str = None
    ) -> dict:
        """
        Entrypoint for transfers.
        The method of preparing media files for transfer to the target cloud storage.

        Args:
            :param sub_directory (str): the name of the subdirectory in the source directory with media content.

        Returns:
            (dict) {
                'status': 'completed'
            }

            (explanation of values)
                (str) 'completed'
                    (this means that the file has been successfully uploaded to the cloud)
                (str) 'not_completed'
                    (this means that an error has occurred the file is not uploaded to the cloud)
        """
        transfers = {}
        statuses = {}
        log.info('[class.%s] preparing media files for transfer to the %s cloud...', __class__.__name__, self.configuration['storage-type'])
        for root, _, files in os.walk(f"{self.configuration['source-directory']}{sub_directory}"):
            for file in files:
                if self.configuration.get('exclude-types', None) in file:
                    os.remove(os.path.join(root, file))
                else:
                    transfers[file] = self.file_upload(
                        source=os.path.join(root, file),
                        destination=self.configuration['destination-directory']
                    )
                    if transfers[file] == 'completed':
                        os.remove(os.path.join(root, file))
                        statuses['status'] = 'completed'
                    else:
                        statuses['status'] = 'not_completed'
                        
        # Removed empty directories 
        if len(os.listdir(f'{self.temporary_dir}{sub_dir_name}')) == 0:
            os.rmdir(f'{self.temporary_dir}{sub_dir_name}')

        log.info(
            '[class.%s] All TRANSFERS: %s',
            __class__.__name__,
            transfers
        )
        return status

    def file_upload(
        self,
        source: str = None,
        destination: str = None
    ) -> Union[str, None]:
        """
        The method of uploading the contents of the target directory
        to the cloud or local directory.

        Args:
            :param source (str): the path to the local file to transfer to the target storage.
            :param destination (str): the name of the target directory in the destination storage.

        Returns:
            (str) 'uploaded'
                or
            None
        """
        log.info(
            '[class.%s] starting upload file %s to %s//:%s',
            __class__.__name__,
            source,
            self.storage['type'],
            destination
        )

        if self.storage['type'] == "local":
            return "saved"

        if self.storage['type'] == 'mega':
            directory = f"{self.storage['cloud_root_path']}/{destination}"
            try:
                mega_folder = self.mega_client.find(
                    directory,
                    exclude_deleted=True
                )
                if not mega_folder:
                    self.mega_client.create_folder(
                        directory
                    )
                response = self.mega_client.upload(
                    source,
                    mega_folder[0]
                )
                log.info(
                    '[class.%s] %s successful transferred',
                    __class__.__name__,
                    response
                )
                return "uploaded"

            # pylint: disable=W0718
            # because the mega library does not contain exceptions
            except Exception as mega_exception:
                log.error(
                    '[class.%s] error when uploading via the mega api: %s',
                    __class__.__name__,
                    mega_exception
                )
                log.warning(
                    '[class.%s] trying again file_upload()',
                    __class__.__name__,
                )
                self.file_upload(
                    source,
                    destination,
                )

        if self.storage['type'] == 'dropbox':
            with open(source, 'rb') as file_transfer:
                response = self.dropbox_client.files_upload(
                    file_transfer.read(),
                    f'/{destination}/{source.split("/")[-1]}'
                )
                log.info(
                    '[class.%s] %s successful transferred',
                    __class__.__name__,
                    response
                )
            file_transfer.close()
            return "uploaded"

        return None
