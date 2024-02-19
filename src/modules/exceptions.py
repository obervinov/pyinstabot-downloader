"""
This module contains custom exceptions for the application.
"""


class InvalidPostId(Exception):
    """
    Exception raised when the post id is invalid.
    """
    def __init__(self, post_id):
        self.post_id = post_id
        self.message = f"Invalid post id: {post_id}"
        super().__init__(self.message)


class InvalidPostLink(Exception):
    """
    Exception raised when the post link is invalid.
    """
    def __init__(self, link):
        self.link = link
        self.message = f"Invalid post link: {link}"
        super().__init__(self.message)
