"""
This module contains custom exceptions that are used in the application.
"""


class FailedMessagesStatusUpdater(Exception):
    """
    Exception raised when the status of the messages could not be updated.
    """
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


class FailedCreateDownloaderInstance(Exception):
    """
    Exception raised when the downloader instance could not be initialized.
    """
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


class FailedInitUploaderInstance(Exception):
    """
    Exception raised when the uploader instance could not be initialized.
    """
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


class WrongVaultInstance(Exception):
    """
    Exception raised when the vault instance is not correct.
    """
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


class FailedAuthInstagram(Exception):
    """
    Exception raised when the authentication of the Instaloader instance failed.
    """
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)
§