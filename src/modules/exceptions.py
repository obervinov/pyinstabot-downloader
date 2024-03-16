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
