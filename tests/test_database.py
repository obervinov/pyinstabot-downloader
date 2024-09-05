"""
This module contains tests for the database module.
"""

import os
import sys
import json
import importlib
from datetime import datetime
from collections import defaultdict
import pytest
import psycopg2
from psycopg2 import pool
from src.modules.database import DatabaseClient
from src.modules.tools import get_hash


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
    Checking the database connection
    """
    _ = postgres_instance
    database = DatabaseClient(vault=vault_instance, db_role=namespace)
    connection = database.get_connection()
    assert isinstance(connection, psycopg2.extensions.connection)
    assert not connection.closed
    database.close_connection(connection)


@pytest.mark.order(6)
def test_messages_queue(namespace, vault_instance):
    """
    Checking the addition of a message to the queue and extraction of a message from the queue
    """
    data = {
        'user_id': '12345',
        'post_id': 'qwerty123',
        'post_url': 'https://www.instagram.com/p/qwerty123/',
        'post_owner': 'johndoe',
        'link_type': 'post',
        'message_id': '111111',
        'chat_id': 'xyz',
        'scheduled_time': '2022-01-01 12:00:00',
        'download_status': 'not started',
        'upload_status': 'not started'
    }
    database = DatabaseClient(vault=vault_instance, db_role=namespace)
    status = database.add_message_to_queue(data=data)

    # Check the addition of a message to the queue
    queue_message = database.get_message_from_queue(scheduled_time=data['scheduled_time'])
    queue_item = {}
    queue_item['user_id'] = queue_message[1]
    queue_item['post_id'] = queue_message[2]
    queue_item['post_url'] = queue_message[3]
    queue_item['post_owner'] = queue_message[4]
    queue_item['link_type'] = queue_message[5]
    queue_item['message_id'] = queue_message[6]
    queue_item['chat_id'] = queue_message[7]
    queue_item['scheduled_time'] = queue_message[8]
    queue_item['download_status'] = queue_message[9]
    queue_item['upload_status'] = queue_message[10]
    assert status == f"{data['message_id']}: added to queue"
    assert queue_item == data


@pytest.mark.order(7)
def test_change_message_state_in_queue(namespace, vault_instance, postgres_instance):
    """
    Checking the change of the message state in the queue
    """
    _, cursor = postgres_instance
    data = {
        'user_id': '12345',
        'post_id': 'qwerty456',
        'post_url': 'https://www.instagram.com/p/qwerty456/',
        'post_owner': 'johndoe',
        'link_type': 'post',
        'message_id': '222222',
        'chat_id': 'xyz',
        'scheduled_time': '2022-01-01 12:00:00',
        'download_status': 'not started',
        'upload_status': 'not started'
    }
    database = DatabaseClient(vault=vault_instance, db_role=namespace)
    database.update_message_state_in_queue(
        post_id='qwerty456',
        state='processed',
        download_status='completed',
        upload_status='completed',
        post_owner='johndoe'
    )

    # Check the change of the message state in the queue
    status = database.update_message_state_in_queue(
        message_id=data['message_id'],
        state='downloaded',
        download_status='completed',
        upload_status='completed',
        post_owner='johndoe'
    )
    assert status == f"{data['message_id']}: processed"

    # Check records in database
    cursor.execute("SELECT post_id FROM queue WHERE post_id = 'qwerty456'")
    record_queue = cursor.fetchall()
    assert record_queue is None
    cursor.execute("SELECT post_id, state, upload_status, download_status  FROM processed WHERE post_id = 'qwerty456'")
    record_processed = cursor.fetchall()
    assert record_processed is not None
    assert record_processed[0][0] == 'qwerty456'
    assert record_processed[0][1] == 'processed'
    assert record_processed[0][2] == 'completed'
    assert record_processed[0][3] == 'completed'


@pytest.mark.order(8)
def test_change_message_schedule_time_in_queue(namespace, vault_instance, postgres_instance):
    """
    Checking the change of the message schedule time in the queue
    """
    _, cursor = postgres_instance
    data = {
        'user_id': '12345',
        'post_id': 'qwerty789',
        'post_url': 'https://www.instagram.com/p/qwerty789/',
        'post_owner': 'johndoe',
        'link_type': 'post',
        'message_id': '333333',
        'chat_id': 'xyz',
        'scheduled_time': '2022-01-01 12:00:00',
        'download_status': 'not started',
        'upload_status': 'not started'
    }
    database = DatabaseClient(vault=vault_instance, db_role=namespace)
    database.add_message_to_queue(data=data)

    # Check the change of the message schedule time in the queue
    status = database.update_schedule_time_in_queue(
        post_id='qwerty789',
        user_id='12345',
        scheduled_time='2022-01-02 13:00:00'
    )
    assert status == f"{data['post_id']}: scheduled time updated"

    # Check records in database
    cursor.execute("SELECT scheduled_time FROM queue WHERE post_id = 'qwerty789'")
    record_queue = cursor.fetchall()
    assert record_queue is not None
    assert record_queue[0][0] == datetime.strptime('2022-01-02 13:00:00', '%Y-%m-%d %H:%M:%S')


@pytest.mark.order(9)
def test_get_user_queue(namespace, vault_instance):
    """
    Checking the extraction of the user queue
    """
    user_id = '111111'
    data = [
        {
            'user_id': user_id,
            'post_id': 'qwerty123',
            'post_url': 'https://www.instagram.com/p/qwerty123/',
            'post_owner': 'johndoe',
            'link_type': 'post',
            'message_id': '111111',
            'chat_id': 'xyz',
            'scheduled_time': '2022-01-01 12:00:00',
            'download_status': 'not started',
            'upload_status': 'not started'
        },
        {
            'user_id': user_id,
            'post_id': 'qwerty456',
            'post_url': 'https://www.instagram.com/p/qwerty456/',
            'post_owner': 'johndoe',
            'link_type': 'post',
            'message_id': '222222',
            'chat_id': 'xyz',
            'scheduled_time': '2022-01-01 12:00:00',
            'download_status': 'not started',
            'upload_status': 'not started'
        },
        {
            'user_id': user_id,
            'post_id': 'qwerty789',
            'post_url': 'https://www.instagram.com/p/qwerty789/',
            'post_owner': 'johndoe',
            'link_type': 'post',
            'message_id': '333333',
            'chat_id': 'xyz',
            'scheduled_time': '2022-01-02 13:00:00',
            'download_status': 'not started',
            'upload_status': 'not started'
        }
    ]
    database = DatabaseClient(vault=vault_instance, db_role=namespace)
    for message in data:
        status = database.add_message_to_queue(data=message)
        assert status == f"{message['message_id']}: added to queue"

    # Validate the extraction of the user queue
    user_queue = database.get_user_queue(user_id='111111')
    expected_response = defaultdict(list)
    for entry in data:
        expected_response[entry['user_id']].append({
            'post_id': entry['post_id'],
            'scheduled_time': entry['scheduled_time']
        })
    expected_response = dict(expected_response)
    assert user_queue is not None
    assert len(user_queue.get(user_id, [])) == len(data)
    assert user_queue == expected_response


@pytest.mark.order(10)
def test_get_user_processed_data(namespace, vault_instance):
    """
    Checking the extraction of the user processed data
    """
    user_id = '111111'
    # Marked messages from previous tests
    mark_processed = ['qwerty123', 'qwerty456', 'qwerty789']
    database = DatabaseClient(vault=vault_instance, db_role=namespace)
    for item in mark_processed:
        status = database.update_message_state_in_queue(
            post_id=item,
            state='processed',
            download_status='completed',
            upload_status='completed',
            post_owner='johndoe'
        )
        assert status == f"{item}: processed"
    user_processed = database.get_user_processed(user_id=user_id)
    user_queue = database.get_user_queue(user_id=user_id)
    for item in mark_processed:
        assert item not in user_queue.get(user_id, []).values()
        assert item in user_processed.get(user_id, []).values()


@pytest.mark.order(11)
def test_check_message_uniqueness(namespace, vault_instance):
    """
    Checking the uniqueness of the message
    """
    data = {
        'user_id': '123456',
        'post_id': 'qwerty1111',
        'post_url': 'https://www.instagram.com/p/qwerty789/',
        'post_owner': 'johndoe',
        'link_type': 'post',
        'message_id': '333333',
        'chat_id': 'xyz',
        'scheduled_time': '2022-01-02 13:00:00',
        'download_status': 'not started',
        'upload_status': 'not started'
    }
    database = DatabaseClient(vault=vault_instance, db_role=namespace)
    uniqueness = database.check_message_uniqueness(post_id=data['post_id'])
    assert uniqueness is True

    status = database.add_message_to_queue(data=data)
    assert status == f"{data['message_id']}: added to queue"

    _ = database.add_message_to_queue(data=data)
    uniqueness = database.check_message_uniqueness(post_id=data['post_id'])
    assert uniqueness is False


@pytest.mark.order(12)
def test_service_messages(namespace, vault_instance):
    """
    Checking the registration of service messages
    """
    data = {
        'message_id': '444444',
        'chat_id': 'xyz',
        'message_content': 'Test message',
        'message_type': 'status_message',
        'state': 'updated'
    }

    # Keep new status_message
    database = DatabaseClient(vault=vault_instance, db_role=namespace)
    status = database.keep_message(**data)
    assert status == f"{data['message_id']} kept"
    new_message = database.get_considered_message(message_type=data['message_type'], chat_id=data['chat_id'])
    assert new_message[0] == data['message_id']
    assert new_message[1] == data['chat_id']
    assert new_message[4] == get_hash(data['message_content'])
    assert new_message[5] == 'updated'

    # Update exist message
    data['message_content'] = 'Updated message'
    status = database.keep_message(**data)
    assert status == f"{data['message_id']} updated"
    updated_message = database.get_considered_message(message_type=data['message_type'], chat_id=data['chat_id'])
    assert updated_message[0] == data['message_id']
    assert updated_message[1] == data['chat_id']
    assert updated_message[2] != updated_message[3]
    assert updated_message[3] != new_message[3]
    assert updated_message[4] == get_hash(data['message_content'])
    assert updated_message[5] == 'updated'

    # Recreate exist message
    data['message_content'] = 'Recreated message'
    status = database.keep_message(**data, recreate=True)
    assert status == f"{data['message_id']} recreated"
    recreated_message = database.get_considered_message(message_type=data['message_type'], chat_id=data['chat_id'])
    assert recreated_message[0] == data['message_id']
    assert recreated_message[1] == data['chat_id']
    assert recreated_message[2] == recreated_message[3]
    assert recreated_message[2] != updated_message[2]
    assert recreated_message[3] != updated_message[3]
    assert recreated_message[4] == get_hash(data['message_content'])
    assert recreated_message[5] == 'updated'
