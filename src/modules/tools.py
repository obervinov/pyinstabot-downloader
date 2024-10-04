"""This module contains the tools for this python project"""
import os
from typing import Union
import hashlib
from logger import log


def get_hash(data: Union[str, dict] = None) -> str:
    """
    Get a hash of the input data.

    Args:
        data (Union[str, dict]): The data to hash.

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


def check_proxy() -> None:
    """
    Check if the proxy is set up.
    """
    http_proxy = os.environ.get('HTTP_PROXY', None)
    https_proxy = os.environ.get('HTTPS_PROXY', None)
    if http_proxy or https_proxy:
        log.info('[Tools]: Proxy is set up http: %s, https: %s', http_proxy, https_proxy)
    else:
        log.info('[Tools]: Direct connection will be used because the proxy is not set up')
