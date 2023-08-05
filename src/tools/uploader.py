"""
This module processes the content uploaded from Instagram
and uploads the found media files (image, video) to the destination storage.
"""
import os
import dropbox
from mega import Mega
from logger import log


class Uploader:
    """
    This class creates an instance with a connection
    to the target storage for uploading local media content.
    """

    def __init__(
        self,
        storage: dict = None,
        vault: object = None
    ) -> None:
        """
        A Method creates an instance with a connection
        to the target storage for uploading local media content.

        Args:
            :param storage (dict): dictionary with storage parameters.
                :param type (str): type of storage for uploading content 'local'/'dropbox'/'mega'
                :param temporary (str): type of storage for uploading content.
                :param cloud_root_path (str): a subdirectory in the cloud storage for saving content
            :param vault (object): instance of vault for reading authorization data.

        Returns:
            None

        Examples:
            >>> UPLOADER_INSTANCE = Uploader(
                    storage={
                        'type': STORAGE_TYPE,
                        'temporary': TEMPORARY_DIR,
                        'cloud_root_path': BOT_NAME,
                        'exclude_type': STORAGE_EXCLUDE_TYPE
                    },
                    vault=VAULT_CLIENT
                )
        """
        self.storage = storage
        self.temporary_dir = f"{os.getcwd()}/{self.storage['temporary']}"
        self.vault = vault

        log.info(
            '[class.%s] uploader instance init with "%s" target storage',
            __class__.__name__,
            storage['type']
        )

        if self.storage['type'] == 'dropbox':
            self.dropbox_client = dropbox.Dropbox(
                oauth2_access_token=self.vault.read_secret(
                    'configuration/dropbox',
                    'token'
                ),
                timeout=60
            )

        if self.storage['type'] == 'mega':
            self.mega_client = Mega().login(
                self.vault.read_secret(
                  'configuration/mega',
                  'username'
                ),
                self.vault.read_secret(
                  'configuration/mega',
                  'password'
                )
            )

        self._check_incomplete_transfers()

    def _check_incomplete_transfers(
        self,
    ) -> None:
        """
        Method for checking uploads in temp directory
        that for some reason could not be uploaded to the cloud.

        Args:
            None

        Returns:
            None
        """
        log.info(
            '[class.%s] checking the pending uploads in the temporary directory ...',
            __class__.__name__
        )

        for _, artifacts, _ in os.walk(self.temporary_dir):
            for artifact in artifacts:
                log.warning(
                    '[class.%s] an unloaded artifact was found %s',
                    __class__.__name__,
                    artifact
                )
                self.start_upload(os.path.join(artifact))

    def start_upload(
        self,
        sub_dir_name: str = None
    ) -> dict:
        """
        Method of preparing media files for transfer to the target storage (cloud or local).

        Args:
            :param sub_dir_name (str): the name of the subdirectory where the content
                                        itself is located is equivalent to the ID of the post.

        Returns:
            (dict) {
                     '/root/path/shortcode/file1.jpeg': 'uploaded',
                     '/root/path/shortcode/file2.jpeg': None
                   }

            (explanation of values)
                (str) 'uploaded'
                    (this means that the file has been successfully uploaded to the cloud)
                (str) 'None'
                    (this means that an error has occurred the file is not uploaded to the cloud)
                (str) 'saved'
                    (this means that the file must remain in the local (temporary directory))
                    (and it is not required to perform any actions with it)
        """
        transfers = {}

        log.info(
            '[class.%s] preparing media files for transfer to the "%s"',
            __class__.__name__,
            self.storage['type']
        )

        for root, _, files in os.walk(
            f'{self.temporary_dir}{sub_dir_name}'
        ):
            for file in files:
                if self.storage['exclude_type'] and self.storage['exclude_type'] in file:
                    os.remove(
                        os.path.join(root, file)
                    )
                else:
                    transfers[file] = self.file_upload(
                        os.path.join(root, file),
                        sub_dir_name
                    )
                    if transfers[file] == 'uploaded':
                        os.remove(
                            os.path.join(root, file)
                        )

        if len(os.listdir(f'{self.temporary_dir}{sub_dir_name}')) == 0:
            os.rmdir(f'{self.temporary_dir}{sub_dir_name}')

        log.info(
            '[class.%s] All TRANSFERS: %s',
            __class__.__name__,
            transfers
        )
        return transfers

    def file_upload(
        self,
        source: str = None,
        destination: str = None,
        retry_on_failure: bool = False
    ) -> str | None:
        """
        The method of uploading the contents of the target directory
        to the cloud or local directory.

        Args:
            :param source (str): the path to the local file to transfer to the target storage.
            :param destination (str): the name of the target directory in the destination storage.
            :param retry_on_failure (bool): flag to indicate whether to retry on failure.

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
                    self.mega_client.create_folder(directory)
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
                if not retry_on_failure:
                    log.warning(
                        '[class.%s] trying again file_upload()',
                        __class__.__name__,
                    )
                    self.file_upload(
                        source,
                        destination,
                        retry_on_failure=True
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
