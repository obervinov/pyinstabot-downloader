"""
This module stores fixtures for performing tests.
"""
import os
import pytest
from vault import VaultClient


@pytest.fixture(name="vault_url", scope='session')
def fixture_vault_url():
    """Returns the vault url"""
    if os.getenv("CI"):
        return "http://localhost:8200"
    return "http://0.0.0.0:8200"


@pytest.fixture(name="project_name", scope='session')
def fixture_project_name():
    """Returns the project name"""
    return "pyinstabot-downloader"


@pytest.fixture(name="prepare_vault", scope='session')
def fixture_prepare_vault(vault_url, project_name, secret_configuration):
    """Fixture for preparing a new vault server"""
    vc_configurator = VaultClient(
        url=vault_url,
        name=project_name,
        new=True
    )
    vc_configurator.create_namespace(
        name=project_name
    )
    policy = vc_configurator.create_policy(
        name=project_name,
        path='vault/policy.hcl'
    )

    for secret in secret_configuration:
        for key in secret:
            vc_configurator.write_secret(
                path=secret,
                key=key,
                value=secret[key]
            )
    return vc_configurator.create_approle(
        name=project_name,
        path=project_name,
        policy=policy,
        token_ttl='15s'
    )


@pytest.fixture(name="test_configuration", scope='session')
def fixture_test_configuration():
    """Returns the test configuration from the secret"""
    return {
        'instagram': {
            'username': 'user1',
            'password': 'password1'
        },
        'mega': {
            'username': 'user1',
            'password': 'password1'
        },
        'telegram': {
            'token': 'token1'
        },
        'dropbox': {
            'token': 'token1'
        },
        'permissions': {
            '123456789': 'allow'
        }
    }


@pytest.fixture(name="vault_client", scope='session')
def fixture_vault_client(vault_url, prepare_vault, project_name):
    """Returns the client of the secrets"""
    return VaultClient(
            url=vault_url,
            name=project_name,
            approle=prepare_vault
    )


@pytest.fixture(name="link_post", scope='session')
def fixture_link_post():
    """Returns the value of the link to the test post from the environment variable"""
    return os.environ['PYTESTS_INST_POST_LINK']


@pytest.fixture(name="link_profile", scope='session')
def fixture_link_profile():
    """Returns the value of the link to the test profile from the environment variable"""
    return os.environ['PYTESTS_INST_PROFILE_LINK']
