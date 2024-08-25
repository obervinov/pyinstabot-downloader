"""
This module stores fixtures for performing tests.
"""
import os
import sys
import subprocess
import time
import requests
import pytest
import hvac
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
    """
    Prepare a local environment or ci environment and return the URL of the Vault server
    """
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
    return None


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


@pytest.fixture(name="namespace", scope='session')
def fixture_namespace():
    """Returns the project namespace"""
    return "pyinstabot-downloader"


@pytest.fixture(name="policy_path", scope='session')
def fixture_policy_path():
    """Returns the policy path"""
    return "tests/vault/policy.hcl"


@pytest.fixture(name="psql_tables_path", scope='session')
def fixture_psql_tables_path():
    """Returns the path to the postgres sql file with tables"""
    return "tests/postgres/tables.sql"


@pytest.fixture(name="postgres_url", scope='session')
def fixture_postgres_url():
    """Returns the postgres url"""
    return "postgresql://{{username}}:{{password}}@postgres:5432/postgres?sslmode=disable"


@pytest.fixture(name="prepare_vault", scope='session')
def fixture_prepare_vault(vault_url, namespace, policy_path, postgres_url):
    """Returns the vault client"""
    client = hvac.Client(url=vault_url)
    init_data = client.sys.initialize()

    # Unseal the vault
    if client.sys.is_sealed():
        client.sys.submit_unseal_keys(keys=[init_data['keys'][0], init_data['keys'][1], init_data['keys'][2]])
    # Authenticate in the vault server using the root token
    client = hvac.Client(url=vault_url, token=init_data['root_token'])

    # Create policy
    with open(policy_path, 'rb') as policyfile:
        _ = client.sys.create_or_update_policy(
            name=namespace,
            policy=policyfile.read().decode("utf-8"),
        )

    # Create Namespace
    _ = client.sys.enable_secrets_engine(
        backend_type='kv',
        path=namespace,
        options={'version': 2}
    )

    # Prepare AppRole for the namespace
    client.sys.enable_auth_method(
        method_type='approle',
        path=namespace
    )
    _ = client.auth.approle.create_or_update_approle(
        role_name=namespace,
        token_policies=[namespace],
        token_type='service',
        secret_id_num_uses=0,
        token_num_uses=0,
        token_ttl='15s',
        bind_secret_id=True,
        token_no_default_policy=True,
        mount_point=namespace
    )
    approle_adapter = hvac.api.auth_methods.AppRole(client.adapter)

    # Prepare database engine configuration
    client.sys.enable_secrets_engine(
        backend_type='database',
        path='database'
    )

    # Configure database engine
    configuration = client.secrets.database.configure(
        name="postgresql",
        plugin_name="postgresql-database-plugin",
        verify_connection=False,
        allowed_roles=["test-role"],
        username="postgres",
        password="postgres",
        connection_url=postgres_url
    )
    print(f"Configured database engine: {configuration}")

    # Create role for the database
    statement = (
        "CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; "
        "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO \"{{name}}\"; "
        "GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO \"{{name}}\";"
    )
    role = client.secrets.database.create_role(
        name="test-role",
        db_name="postgresql",
        creation_statements=statement,
        default_ttl="1h",
        max_ttl="24h"
    )
    print(f"Created role: {role}")

    # Return the role_id and secret_id
    return {
        'id': approle_adapter.read_role_id(role_name=namespace, mount_point=namespace)["data"]["role_id"],
        'secret-id': approle_adapter.generate_secret_id(role_name=namespace, mount_point=namespace)["data"]["secret_id"]
    }


@pytest.fixture(name="vault_instance", scope='session')
def fixture_vault_instance(vault_url, namespace, prepare_vault):
    """Returns client of the configurator"""
    return VaultClient(
        url=vault_url,
        namespace=namespace,
        auth={
            'type': 'approle',
            'approle': {
                'id': prepare_vault['id'],
                'secret-id': prepare_vault['secret-id']
            }
        }
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
        _ = vault_instance.kv2engine.write_secret(
            path='configuration/database',
            key=key,
            value=value
        )

    _ = vault_instance.kv2engine.write_secret(
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
        _ = vault_instance.kv2engine.write_secret(
            path=f'configuration/users/{user_id}',
            key=key,
            value=value
        )
