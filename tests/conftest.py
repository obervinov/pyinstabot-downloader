"""
This module stores fixtures for performing tests.
"""
import os
import time
import requests
import pytest
import hvac
import psycopg2
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


@pytest.fixture(name="vault_url", scope='session')
def fixture_vault_url():
    """
    Prepare a local environment or ci environment and return the URL of the Vault server

    Returns:
        str: The URL of the Vault server.
    """

    url = "http://0.0.0.0:8200"
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
    """
    Returns the namespace for the tests

    Returns:
        str: The namespace for the tests.
    """
    return "pytest"


@pytest.fixture(name="policy_path", scope='session')
def fixture_policy_path():
    """
    Returns the policy path for the tests

    Returns:
        str: The policy path for the tests.
    """
    return "tests/vault/policy.hcl"


@pytest.fixture(name="psql_tables_path", scope='session')
def fixture_psql_tables_path():
    """
    Returns the path to the postgres sql file with tables

    Returns:
        str: The path to the postgres sql file with tables.
    """
    return "tests/postgres/tables.sql"


@pytest.fixture(name="postgres_url", scope='session')
def fixture_postgres_url():
    """
    Returns the postgres url for the tests

    Returns:
        str: The postgres url.
    """
    return "postgresql://{{username}}:{{password}}@postgres:5432/postgres?sslmode=disable"


@pytest.fixture(name="postgres_instance", scope='session')
def fixture_postgres_instance(psql_tables_path):
    """
    Prepare the postgres database, return the connection and cursor

    Returns:
        tuple: The connection and cursor objects for the postgres database.
    """
    # Prepare database for tests
    psql_connection = psycopg2.connect(
        host='0.0.0.0',
        port=5432,
        user='postgres',
        password='postgres',
        dbname='postgres'
    )
    psql_cursor = psql_connection.cursor()
    with open(psql_tables_path, 'r', encoding='utf-8') as sql_file:
        sql_script = sql_file.read()
        psql_cursor.execute(sql_script)
        psql_connection.commit()
    return psql_connection, psql_cursor


@pytest.fixture(name="prepare_vault", scope='session')
def fixture_prepare_vault(vault_url, namespace, policy_path, postgres_url, postgres_instance):
    """
    Returns the vault client and prepares the vault for the tests

    Returns:
        object: The vault client.
    """
    # Wait for the postgres database to be ready
    _ = postgres_instance

    # Initialize the vault
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
        allowed_roles=["pytest"],
        username="postgres",
        password="postgres",
        connection_url=postgres_url
    )
    print(f"Configured database engine: {configuration}")

    # Create role for the database
    statement = (
        "CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; "
        "ALTER TABLE public.users OWNER TO \"{{name}}\"; "
        "ALTER TABLE public.users_requests OWNER TO \"{{name}}\"; "
        "ALTER TABLE public.messages OWNER TO \"{{name}}\"; "
        "ALTER TABLE public.queue OWNER TO \"{{name}}\"; "
        "ALTER TABLE public.processed OWNER TO \"{{name}}\"; "
        "ALTER TABLE public.migrations OWNER TO \"{{name}}\"; "
        "GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO \"{{name}}\";"
    )
    role = client.secrets.database.create_role(
        name="pytest",
        db_name="postgresql",
        creation_statements=statement,
        default_ttl="1h",
        max_ttl="24h"
    )
    print(f"Created role: {role}")

    # Return the role_id, secret_id and db_role
    return {
        'id': approle_adapter.read_role_id(role_name=namespace, mount_point=namespace)["data"]["role_id"],
        'secret-id': approle_adapter.generate_secret_id(role_name=namespace, mount_point=namespace)["data"]["secret_id"]
    }


@pytest.fixture(name="vault_instance", scope='function')
def fixture_vault_instance(vault_url, namespace, prepare_vault):
    """
    Returns client of the configurator vault

    Returns:
        object: The vault client.
    """
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
    """
    database = {
        'host': '0.0.0.0',
        'port': '5432',
        'database': 'postgres',
        'connections': '10'
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
    bot_configurations = [
        {
            'path': 'configuration/downloader-api',
            'data': {
                'enabled': 'false',
            }
        },
        {
            'path': 'configuration/uploader-api',
            'data': {
                'enabled': 'false',
            }
        }
    ]
    for configuration in bot_configurations:
        for key, value in configuration['data'].items():
            _ = vault_instance.kv2engine.write_secret(
                path=configuration['path'],
                key=key,
                value=value
            )


@pytest.fixture(name="postgres_messages_test_data", scope='session')
def fixture_postgres_messages_test_data(postgres_instance):
    """
    This function sets up test data in the messages table in the postgres database.

    Args:
        postgres_instance: A tuple containing the connection and cursor objects for the postgres database.
    """
    conn, cursor = postgres_instance
    cursor.execute(
        "INSERT INTO messages (message_id, chat_id, created_at, updated_at, message_type, producer, message_content_hash, state) "
        "VALUES ('123456', '123456', '2024-08-27 00:00:00', '2024-08-27 00:00:00', 'status_message', 'pytest', 'hash', 'updating')"
    )
    conn.commit()
