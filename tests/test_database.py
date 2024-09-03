"""
This module contains tests for the database module.
"""

import os
import sys
import json
import importlib
import pytest
import psycopg2
from psycopg2 import pool
from src.modules.database import DatabaseClient


# pylint: disable=too-many-locals
@pytest.mark.order(2)
def test_init_database_client(namespace, vault_instance, vault_configuration_data, postgres_instance):
    """
    Checking an initialized database client
    """
    _ = vault_configuration_data
    _, cursor = postgres_instance
    database = DatabaseClient(vault=vault_instance, db_role=namespace)

    # Check general attributes
    assert isinstance(database.vault, object)
    assert isinstance(database.db_role, str)
    assert isinstance(database.database_connections, pool.SimpleConnectionPool)

    # Check tables creation in the database
    cursor.execute("SELECT * FROM information_schema.tables WHERE table_schema = 'public'")
    tables_list = cursor.fetchall()
    tables_configuration_path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '../src/configs/databases.json'))
    with open(tables_configuration_path, encoding='UTF-8') as config_file:
        database_init_configuration = json.load(config_file)
    for table in database_init_configuration.get('Tables', None):
        if table['name'] not in [table[2] for table in tables_list]:
            assert False

    # Check migrations execution in the database
    cursor.execute("SELECT name, version FROM migrations")
    migrations_list = cursor.fetchall()
    assert len(migrations_list) > 0

    migrations_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../src/migrations'))
    sys.path.append(migrations_dir)
    migration_files = [f for f in os.listdir(migrations_dir) if f.endswith('.py')]
    migration_files.sort()
    for migration_file in migration_files:
        if not migration_file.endswith('.py'):
            assert False
        else:
            migration_module_name = migration_file[:-3]
            migration_module = importlib.import_module(name=migration_module_name)
            version = getattr(migration_module, 'VERSION', migration_module_name)
            name = getattr(migration_module, 'NAME', migration_module_name)
            if (name, version) not in migrations_list:
                print(f"Not found migration {name}:{version} in {migrations_list}")
                assert False


@pytest.mark.order(4)
def test_reset_stale_messages(namespace, vault_instance, postgres_instance, postgres_messages_test_data):
    """
    Checking the reset of stale messages when the database client is initialized
    """
    _, cursor = postgres_instance
    _ = postgres_messages_test_data
    _ = DatabaseClient(vault=vault_instance, db_role=namespace)

    # Check the reset of stale messages
    cursor.execute("SELECT state FROM messages")
    messages_list = cursor.fetchall()
    assert len(messages_list) > 0
    for message in messages_list:
        assert message[0] == 'updated'


@pytest.mark.order(5)
def test_database_connection(namespace, vault_instance, postgres_instance):
    """
    Checking the database connection and disconnection
    """
    _ = postgres_instance
    database = DatabaseClient(vault=vault_instance, db_role=namespace)

    # Check the database connection
    connection = database.get_connection()
    assert isinstance(connection, psycopg2.extensions.connection)
    assert not connection.closed

    # Check the database disconnection
    database.close_connection(connection)
    assert connection == 0


# @pytest.mark.order(6)
# def test_add_message_to_queue(namespace, vault_instance, postgres_instance):
#     """
#     Checking the addition of a message to the queue
#     """
#     _, cursor = postgres_instance
#     data = {
#         'user_id': '12345',
#         'post_id': '67890',
#         'post_url': 'https://www.instagram.com/p/67890/',
#         'post_owner': 'johndoe',
#         'link_type': 'profile',
#         'message_id': 'abcde',
#         'chat_id': 'xyz',
#         'scheduled_time': '2022-01-01 12:00:00',
#         'download_status': 'not started',
#         'upload_status': 'not started'
#     }
#     database = DatabaseClient(vault=vault_instance, db_role=namespace)
#     response = database.add_message_to_queue(data=data)

#     # Check the addition of a message to the queue
#     cursor.execute(
#         "SELECT user_id, post_id, post_url, post_owner, link_type, message_id, chat_id, scheduled_time, download_status, upload_status "
#         "FROM queue WHERE message_id = 'abcde'"
#     )
#     queue_item = cursor.fetchone()
#     assert len(queue_item) > 0
#     assert response == f"{data['message_id']}: added to queue"
#     assert queue_item == (
#         data['user_id'], data['post_id'], data['post_url'],
#         data['post_owner'], data['link_type'], data['message_id'],
#         data['chat_id'], data['scheduled_time'], data['download_status'], data['upload_status']
#     )
