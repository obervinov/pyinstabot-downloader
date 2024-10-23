"""This module contains the tools for this python project"""
import hashlib


def get_hash(data: str | dict = None) -> str:
    """
    Get a hash of the input data.

    Args:
        data (str | dict): The data to hash.

    Returns:
        str: A hash of the content.

    Examples:
        >>> get_hash('Hello, world!')
        '2ef7bde608ce5404e97d5f042f95f89f1c232871d3d7'
    """
    hasher = hashlib.sha256()
    if isinstance(data, dict):
        data = str(data)
    hasher.update(data.encode('utf-8'))
    return hasher.hexdigest()
