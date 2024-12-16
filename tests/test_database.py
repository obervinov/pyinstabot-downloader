"""
This module contains tests for the database module.
"""
import os
import sys
import json
import importlib
from datetime import datetime, timedelta
import pytest
import psycopg2
from psycopg2 import pool
from src.modules.tools import get_hash
from src.modules.database import DatabaseClient


# pylint: disable=too-many-locals
@pytest.mark.order(2)
def test_init_database_client(vault_configuration_data, postgres_instance, database_class):
    """
    Checking an initialized database client
    """
    _ = vault_configuration_data
    _, cursor = postgres_instance

    # Check general attributes
    assert isinstance(database_class.vault, object)
    assert isinstance(database_class.db_role, str)
    assert isinstance(database_class.database_connections, pool.SimpleConnectionPool)

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
def test_reset_stale_messages(postgres_instance, postgres_messages_test_data, vault_instance, namespace):
    """
    Checking the reset of stale messages when the database client is initialized
    """
    _, cursor = postgres_instance
    _ = postgres_messages_test_data
    # Reinitialize the database class for triggering the reset of stale messages
    # Create new instance of the DatabaseClient class because private method _reset_stale_records() is launched only when the class is initialized
    _ = DatabaseClient(vault=vault_instance, db_role=namespace)

    # Check the reset of stale messages
    cursor.execute("SELECT state FROM messages")
    messages_list = cursor.fetchall()
    assert len(messages_list) > 0
    for message in messages_list:
        assert message[0] == 'updated'


@pytest.mark.order(5)
def test_database_connection(postgres_instance, database_class):
    """
    Checking the database connection
    """
    _ = postgres_instance
    connection = database_class.get_connection()
    assert isinstance(connection, psycopg2.extensions.connection)
    assert not connection.closed
    database_class.close_connection(connection)


@pytest.mark.order(6)
def test_messages_queue(database_class):
    """
    Checking the addition of a message to the queue and extraction of a message from the queue
    """
    data = {
        'user_id': 'test_case_6',
        'post_id': 'test_case_6',
        'post_url': 'https://www.instagram.com/p/test_case_6',
        'post_owner': 'test_case_6',
        'link_type': 'post',
        'message_id': 'test_case_6',
        'chat_id': 'test_case_6',
        'scheduled_time': '2022-01-01 12:00:00',
        'download_status': 'not started',
        'upload_status': 'not started'
    }
    status = database_class.add_message_to_queue(data=data)

    # Check the addition of a message to the queue
    queue_message = database_class.get_message_from_queue(scheduled_time=data['scheduled_time'])
    queue_item = {}
    queue_item['user_id'] = queue_message[1]
    queue_item['post_id'] = queue_message[2]
    queue_item['post_url'] = queue_message[3]
    queue_item['post_owner'] = queue_message[4]
    queue_item['link_type'] = queue_message[5]
    queue_item['message_id'] = queue_message[6]
    queue_item['chat_id'] = queue_message[7]
    queue_item['scheduled_time'] = datetime.strftime(queue_message[8], '%Y-%m-%d %H:%M:%S')
    queue_item['download_status'] = queue_message[9]
    queue_item['upload_status'] = queue_message[10]
    assert status == f"{data['message_id']}: added to queue"
    assert queue_item == data


@pytest.mark.order(7)
def test_change_message_state_in_queue(database_class, postgres_instance):
    """
    Checking the change of the message state in the queue
    """
    _, cursor = postgres_instance
    data = {
        'user_id': 'test_case_7',
        'post_id': 'test_case_7',
        'post_url': 'https://example.com/p/test_case_7',
        'post_owner': 'test_case_7',
        'link_type': 'post',
        'message_id': 'test_case_7',
        'chat_id': 'test_case_7',
        'scheduled_time': '2022-01-01 12:00:00',
        'download_status': 'not started',
        'upload_status': 'not started'
    }
    status = database_class.add_message_to_queue(data=data)
    assert status == f"{data['message_id']}: added to queue"

    # Check the change of the message state in the queue
    updated_status = database_class.update_message_state_in_queue(
        post_id=data['post_id'],
        state='processed',
        download_status='completed',
        upload_status='completed',
        post_owner=data['post_owner']
    )
    assert updated_status == f"{data['message_id']}: processed"

    # Check records in database
    cursor.execute(f"SELECT post_id FROM queue WHERE post_id = '{data['post_id']}'")
    record_queue = cursor.fetchall()
    assert record_queue == []
    cursor.execute(f"SELECT post_id, state, upload_status, download_status  FROM processed WHERE post_id = '{data['post_id']}'")
    record_processed = cursor.fetchall()
    assert record_processed != []
    assert record_processed[0][0] == data['post_id']
    assert record_processed[0][1] == 'processed'
    assert record_processed[0][2] == 'completed'
    assert record_processed[0][3] == 'completed'


@pytest.mark.order(8)
def test_change_message_schedule_time_in_queue(database_class, postgres_instance):
    """
    Checking the change of the message schedule time in the queue
    """
    _, cursor = postgres_instance
    data = {
        'user_id': 'test_case_8',
        'post_id': 'test_case_8',
        'post_url': 'https://example.com/p/test_case_8',
        'post_owner': 'test_case_8',
        'link_type': 'post',
        'message_id': 'test_case_8',
        'chat_id': 'test_case_8',
        'scheduled_time': '2022-01-01 12:00:00',
        'download_status': 'not started',
        'upload_status': 'not started'
    }
    status = database_class.add_message_to_queue(data=data)
    assert status == f"{data['message_id']}: added to queue"

    # Check the change of the message schedule time in the queue
    status = database_class.update_schedule_time_in_queue(
        post_id=data['post_id'],
        user_id=data['user_id'],
        scheduled_time='2022-01-02 13:00:00'
    )
    assert status == f"{data['post_id']}: scheduled time updated"

    # Check records in database
    cursor.execute(f"SELECT scheduled_time FROM queue WHERE post_id = '{data['post_id']}'")
    record_queue = cursor.fetchall()
    assert record_queue is not None
    assert record_queue[0][0] == datetime.strptime('2022-01-02 13:00:00', '%Y-%m-%d %H:%M:%S')


@pytest.mark.order(9)
def test_get_user_queue(database_class):
    """
    Checking the extraction of the user queue
    """
    user_id = 'test_case_9'
    timestamp = datetime.now()
    data = [
        {
            'user_id': user_id,
            'post_id': 'test_case_9_1',
            'post_url': 'https://example.com/p/test_case_9_1',
            'post_owner': 'test_case_9',
            'link_type': 'post',
            'message_id': 'test_case_9_1',
            'chat_id': 'test_case_9',
            'scheduled_time': timestamp + timedelta(hours=1),
            'download_status': 'not started',
            'upload_status': 'not started'
        },
        {
            'user_id': user_id,
            'post_id': 'test_case_9_2',
            'post_url': 'https://example.com/p/test_case_9_2',
            'post_owner': 'test_case_9',
            'link_type': 'post',
            'message_id': 'test_case_9_2',
            'chat_id': 'test_case_9',
            'scheduled_time': timestamp - timedelta(hours=2),
            'download_status': 'not started',
            'upload_status': 'not started'
        },
        {
            'user_id': user_id,
            'post_id': 'test_case_9_3',
            'post_url': 'https://example.com/p/test_case_9_3',
            'post_owner': 'test_case_9',
            'link_type': 'post',
            'message_id': 'test_case_9_3',
            'chat_id': 'test_case_9',
            'scheduled_time': timestamp + timedelta(hours=3),
            'download_status': 'not started',
            'upload_status': 'not started'
        }
    ]
    for message in data:
        status = database_class.add_message_to_queue(data=message)
        assert status == f"{message['message_id']}: added to queue"

    # Validate the extraction of the user queue (now directly a list)
    user_queue = database_class.get_user_queue(user_id=user_id)
    expected_response = sorted([
        {
            'post_id': entry['post_id'],
            'scheduled_time': entry['scheduled_time']
        }
        for entry in data
    ], key=lambda x: x['scheduled_time'])

    assert user_queue is not None
    assert len(user_queue) == len(data)
    assert user_queue == expected_response


@pytest.mark.order(10)
def test_get_user_processed_data(database_class, postgres_instance):
    """
    Checking the extraction of the user processed data
    """
    _, cursor = postgres_instance
    user_id = 'test_case_10'
    timestamp = datetime.now()
    data = [
        {
            'user_id': user_id,
            'post_id': 'test_case_10_1',
            'post_url': 'https://example.com/p/test_case_10_1',
            'post_owner': 'test_case_10',
            'link_type': 'post',
            'message_id': 'test_case_10_1',
            'chat_id': 'test_case_10',
            'scheduled_time': timestamp + timedelta(hours=1),
            'download_status': 'not started',
            'upload_status': 'not started'
        },
        {
            'user_id': user_id,
            'post_id': 'test_case_10_2',
            'post_url': 'https://example.com/p/test_case_10_2',
            'post_owner': 'test_case_10',
            'link_type': 'post',
            'message_id': 'test_case_10_2',
            'chat_id': 'test_case_10',
            'scheduled_time': timestamp - timedelta(hours=2),
            'download_status': 'not started',
            'upload_status': 'not started'
        },
        {
            'user_id': user_id,
            'post_id': 'test_case_10_3',
            'post_url': 'https://example.com/p/test_case_10_3',
            'post_owner': 'test_case_10',
            'link_type': 'post',
            'message_id': 'test_case_10_3',
            'chat_id': 'test_case_10',
            'scheduled_time': timestamp + timedelta(hours=3),
            'download_status': 'not started',
            'upload_status': 'not started'
        }
    ]
    for message in data:
        status = database_class.add_message_to_queue(data=message)
        assert status == f"{message['message_id']}: added to queue"
        status = database_class.update_message_state_in_queue(
            post_id=message['post_id'],
            state='processed',
            download_status='completed',
            upload_status='completed',
            post_owner=message['post_owner']
        )
        assert status == f"{message['post_id']}: processed"

    user_processed = database_class.get_user_processed(user_id=user_id)
    user_queue = database_class.get_user_queue(user_id=user_id)

    for message in data:
        if user_queue:
            for q_message in user_queue:
                assert message['post_id'] != q_message['post_id']

        if user_processed:
            found = False
            assert len(user_processed) == len(data)
            for p_message in user_processed:
                if message['post_id'] == p_message['post_id']:
                    found = True
            if not found:
                print(f"Message {message['post_id']} not found in processed: {user_processed}")
                assert False
            else:
                assert True
        else:
            cursor.execute("SELECT * FROM processed")
            print(cursor.fetchall())
            assert False


@pytest.mark.order(11)
def test_check_message_uniqueness(database_class):
    """
    Checking the uniqueness of the message
    """
    data = {
        'user_id': 'test_case_11',
        'post_id': 'test_case_11',
        'post_url': 'https://example.com/p/test_case_11',
        'post_owner': 'test_case_11',
        'link_type': 'post',
        'message_id': 'test_case_11',
        'chat_id': 'test_case_11',
        'scheduled_time': '2022-01-02 13:00:00',
        'download_status': 'not started',
        'upload_status': 'not started'
    }
    uniqueness = database_class.check_message_uniqueness(post_id=data['post_id'], user_id=data['user_id'])
    assert uniqueness is True

    status = database_class.add_message_to_queue(data=data)
    assert status == f"{data['message_id']}: added to queue"
    uniqueness = database_class.check_message_uniqueness(post_id=data['post_id'], user_id=data['user_id'])
    assert uniqueness is False


@pytest.mark.order(12)
def test_service_messages(database_class):
    """
    Checking the registration of service messages
    """
    data = {
        'message_id': 'test_case_12',
        'chat_id': 'test_case_12',
        'message_content': 'Test case 12',
        'message_type': 'status_message',
        'state': 'updated'
    }

    # Keep new status_message
    status = database_class.keep_message(**data)
    assert status == f"{data['message_id']} kept"
    new_message = database_class.get_considered_message(message_type=data['message_type'], chat_id=data['chat_id'])
    assert new_message[0] == data['message_id']
    assert new_message[1] == data['chat_id']
    assert new_message[4] == get_hash(data['message_content'])
    assert new_message[5] == 'added'

    # Update exist message
    data['message_content'] = 'Updated message'
    status = database_class.keep_message(**data)
    assert status == f"{data['message_id']} updated"
    updated_message = database_class.get_considered_message(message_type=data['message_type'], chat_id=data['chat_id'])
    assert updated_message[0] == data['message_id']
    assert updated_message[1] == data['chat_id']
    assert updated_message[2] != updated_message[3]
    assert updated_message[3] != new_message[3]
    assert updated_message[4] == get_hash(data['message_content'])
    assert updated_message[5] == 'updated'

    # Recreate exist message
    data['message_content'] = 'Recreated message'
    status = database_class.keep_message(**data, recreated=True)
    assert status == f"{data['message_id']} recreated"
    recreated_message = database_class.get_considered_message(message_type=data['message_type'], chat_id=data['chat_id'])
    assert recreated_message[0] == data['message_id']
    assert recreated_message[1] == data['chat_id']
    assert recreated_message[2] == recreated_message[3]
    assert recreated_message[2] != updated_message[2]
    assert recreated_message[3] != updated_message[3]
    assert recreated_message[4] == get_hash(data['message_content'])
    assert recreated_message[5] == 'updated'
