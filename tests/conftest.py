"""
This module stores fixtures for performing tests.
"""
import os
import sys
import subprocess
import time
import requests
import pytest
# pylint: disable=E0401
from vault import VaultClient


def pytest_configure(config):
    """
    Configure Pytest by adding a custom marker for setting the execution order of tests.

    This function is called during Pytest's configuration phase and is used to extend Pytest's
    functionality by adding custom markers. In this case, it adds a "order" marker to specify
    the execution order of tests.

    Parameters:
    - config (object): The Pytest configuration object.

    Example Usage:
    @pytest.mark.order(1)
    def test_example():
        # test code
    """
    config.addinivalue_line("markers", "order: Set the execution order of tests")


@pytest.fixture(name="prepare_dev_environment", scope='session')
def fixture_prepare_dev_environment():
    if not os.getenv("CI"):
        if not os.getenv("TG_USERID"):
            print("You need to set the TG_USER_ID environment variable to run the tests (telegram user-id)")
            sys.exit(1)
        if not os.getenv("TG_TOKEN"):
            print("You need to set the TG_TOKEN environment variable to run the tests (telegram token)")
            sys.exit(1)
        command = (
            "vault=$(docker ps -a | grep vault | awk '{print $1}') && "
            "bot=$(docker ps -a | grep pyinstabot-downloader | awk '{print $1}') && "
            "[ -n '$vault' ] && docker container rm -f $vault && "
            "[ -n '$bot' ] && docker container rm -f $bot && "
            "docker compose -f docker-compose.dev.yml up -d"
        )
        with subprocess.Popen(command, shell=True):
            print("Running dev environment...")
        return 'ready'

@pytest.fixture(name="vault_url", scope='session')
def fixture_vault_url(prepare_dev_environment):
    """Prepare a local environment or ci environment and return the URL of the Vault server"""
    _ = prepare_dev_environment
    # prepare vault for local environment
    if not os.getenv("CI"):
        url = "http://0.0.0.0:8200"
    # prepare vault for ci environment
    else:
        url = "http://localhost:8200"
    # checking the availability of the vault server
    while True:
        try:
            response = requests.get(url=url, timeout=3)
            if 200 <= response.status_code < 500:
                break
        except requests.exceptions.RequestException as exception:
            print(f"Waiting for the vault server: {exception}")
            time.sleep(5)
    return url


@pytest.fixture(name="name", scope='session')
def fixture_name():
    """Returns the project name"""
    return "pyinstabot-downloader"


@pytest.fixture(name="policy_path", scope='session')
def fixture_policy_path():
    """Returns the policy path"""
    return "tests/vault/policy.hcl"


@pytest.fixture(name="vault_approle", scope='session')
def fixture_vault_approle(vault_url, name, policy_path):
    """Prepare a temporary Vault instance and return the Vault client"""
    configurator = VaultClient(
                url=vault_url,
                name=name,
                new=True
    )
    namespace = configurator.create_namespace(
            name=name
    )
    policy = configurator.create_policy(
            name=name,
            path=policy_path
        )
    return configurator.create_approle(
        name=name,
        path=namespace,
        policy=policy
    )


@pytest.fixture(name="vault_instance", scope='session')
def fixture_vault_instance(vault_url, vault_approle, name):
    """Returns an initialized vault instance"""
    return VaultClient(
        url=vault_url,
        name=name,
        approle=vault_approle
    )


@pytest.fixture(name="vault_configuration_data", scope='session')
def fixture_vault_configuration_data(vault_instance):
    """
    This function sets up a database configuration in the vault_instance object.

    Args:
        vault_instance: An instance of the Vault class.

    Returns:
        None
    """
    database = {
        'host': 'postgres',
        'port': '5432',
        'user': 'python',
        'password': 'python',
        'database': 'pyinstabot-downloader'
    }
    for key, value in database.items():
        _ = vault_instance.write_secret(
            path='configuration/database',
            key=key,
            value=value
        )

    _ = vault_instance.write_secret(
        path='configuration/telegram',
        key='token',
        value=os.getenv("TG_TOKEN")
    )

    user_attributes = {
        "status": "allowed",
        "roles": [
            "get_post_role",
            "get_posts_list_role",
            "get_queue_role",
            "get_history_role"
        ],
        "requests": {
            "requests_per_day": 10,
            "requests_per_hour": 1,
            "random_shift_minutes": 15
        }
    }
    user_id = os.getenv("TG_USERID")
    for key, value in user_attributes.items():
        _ = vault_instance.write_secret(
            path=f'configuration/users/{user_id}',
            key=key,
            value=value
        )

    test_owner = {
        "eiD5aech8Oh": "downloaded",
        "eiD5aech8Oa": "downloaded",
        "eiD5aech8Oq": "downloaded",
        "eiD5aech8Ol": "downloaded",
        "eiD5aech8Op": "downloaded",
        "eiD5aech8Oy": "downloaded"
    }
    for key, value in test_owner.items():
        _ = vault_instance.write_secret(
            path='history/testOwner',
            key=key,
            value=value
        )
