"""This module contains a class for interacting with a PostgreSQL database using psycopg2."""
import os
import sys
import importlib
import json
from typing import Union
from datetime import datetime, timedelta
import psycopg2
from logger import log
from .tools import get_hash


class DatabaseClient:
    """
    A class that represents a client for interacting with a PostgreSQL database.

    Args:
        vault (object): An object representing a HashiCorp Vault client for retrieving secrets.

    Attributes:
        database_connection (psycopg2.extensions.connection): A connection to the PostgreSQL database.
        cursor (psycopg2.extensions.cursor): A cursor for executing SQL queries on the database.
        vault (object): An object representing a HashiCorp Vault client for retrieving secrets.

    Returns:
        None

    Example:
        To create a new instance of the DatabaseClient class, you can use the following code:
        >>> from modules.database import DatabaseClient
        >>> from modules.vault import VaultClient
        >>> vault = VaultClient()
        >>> db_client = DatabaseClient(vault=vault)
    """

    def __init__(
        self,
        vault: object = None,
        environment: str = None
    ) -> None:
        """
        Initializes a new instance of the Database class.

        Args:
            vault (object): An instance of the Vault class.
            environment (str): The environment to use for the database connection.

        Parameters:
            host (str): The hostname of the database server.
            port (int): The port number of the database server.
            user (str): The username to use when connecting to the database.
            password (str): The password to use when connecting to the database.
            database (str): The name of the database to connect to.
            log (object): An object representing a logger for logging messages.

        Returns:
            None

        Examples:
            To create a new instance of the Database class:
            >>> from modules.database import Database
            >>> from modules.vault import Vault
            >>> vault = Vault()
            >>> db = Database(vault)
        """
        if environment:
            db_configuration = vault.read_secret(path=f"configuration/database-{environment}")
        else:
            db_configuration = vault.read_secret(path='configuration/database')
        log.info('[class.%s]: Initializing database connection to %s:%s', __class__.__name__, db_configuration['host'], db_configuration['port'])

        self.database_connection = psycopg2.connect(
            host=db_configuration['host'],
            port=db_configuration['port'],
            user=db_configuration['user'],
            password=db_configuration['password'],
            database=db_configuration['database']
        )
        self.cursor = self.database_connection.cursor()
        self.vault = vault
        self._prepare_db()
        self._migrations()

    def _prepare_db(self) -> None:
        """
        Creates and initializes the necessary tables in the database.

        Args:
            None

        Parameters:
            None

        Returns:
            None

        Examples:
            To create and initialize the necessary tables in the database, call the method like this:
            >>> db = Database()
            >>> db._prepare_db()
        """
        configuration_path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '../configs/databases.json'))
        with open(configuration_path, encoding='UTF-8') as config_file:
            database_init_configuration = json.load(config_file)

        # Create database if does not exist
        for table in database_init_configuration['Tables']:
            log.info('[class.%s] Preparing database: table `%s`...', __class__.__name__, table['name'])
            self._create_table(
                table_name=table['name'],
                columns="".join(f"{column}" for column in table['columns'])
            )
            log.info('[class.%s] Preparing database: table `%s` has been created', __class__.__name__, table['name'])

        # Data seeding
        for data in database_init_configuration['DataSeeding']:
            log.info('[class.%s] Preparing database: data seeding for table `%s`...', __class__.__name__, data['table'])
            self._insert(
                table_name=data['table'],
                columns=tuple(data['data'].keys()),
                values=tuple(data['data'].values())
            )
            log.info('[class.%s] Preparing database: data seeding for table `%s` has been completed', __class__.__name__, data['table'])

    def _migrations(self) -> None:
        """
        Executes all pending database migrations.

        Args:
            None

        Parameters:
            None

        Returns:
            None

        Examples:
            >>> db = Database()
            >>> db._migrations()
        """
        log.info('[class.%s] Reading database migrations...', __class__.__name__)
        migrations_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../migrations'))
        sys.path.append(migrations_dir)
        for migration_file in os.listdir(migrations_dir):
            log.info('[class.%s] Executing migration: %s...', __class__.__name__, migration_file)
            if migration_file.endswith('.py'):
                migration_module_name = migration_file[:-3]
                if not self._is_migration_executed(migration_module_name):
                    migration_module = importlib.import_module(migration_module_name)
                    migration_module.execute(self)
                    version = getattr(migration_module, 'VERSION', migration_module_name)
                    self._mark_migration_as_executed(migration_module_name, version)
                else:
                    log.info('[class.%s] the %s migration has already been executed and was skipped', __class__.__name__, migration_module_name)

    def _is_migration_executed(
        self,
        migration_name: str = None
    ) -> bool:
        """
        Check if a migration has already been executed.

        Args:
            migration_name (str): The name of the migration to check.

        Returns:
            bool: True if the migration has been executed, False otherwise.

        Examples:
            >>> db = Database()
            >>> db._is_migration_executed('create_users_table')
            True
        """
        self.cursor.execute(f"SELECT id FROM migrations WHERE name = '{migration_name}'")
        return self.cursor.fetchone() is not None

    def _mark_migration_as_executed(
        self,
        migration_name: str = None,
        version: str = None
    ) -> None:
        """
        Inserts a migration into the migrations table to mark it as executed.

        Args:
            migration_name (str): The name of the migration to mark as executed.

        Returns:
            None

        Examples:
            >>> _mark_migration_as_executed('create_users_table')
        """
        self.cursor.execute(f"INSERT INTO migrations (name, version) VALUES ('{migration_name}', '{version}')")
        self.database_connection.commit()

    def _create_table(
        self,
        table_name: str = None,
        columns: str = None
    ) -> None:
        """
        Create a new table in the database with the given name and columns.

        Args:
            table_name (str): The name of the table to create.
            columns (str): A string containing the column definitions for the table.

        Returns:
            None

        Examples:
            To create a new table called 'users' with columns 'id' and 'name', you can call the method like this:

            >>> _create_table('users', 'id INTEGER PRIMARY KEY, name TEXT')
        """
        self.cursor.execute(f"CREATE TABLE IF NOT EXISTS {table_name} ({columns})")
        self.database_connection.commit()

    def _insert(
        self,
        table_name: str = None,
        columns: tuple = None,
        values: tuple = None
    ) -> None:
        """
        Inserts a new row into the specified table with the given columns and values.

        Args:
            table_name (str): The name of the table to insert the row into.
            columns (tuple): A tuple containing the names of the columns to insert the values into.
            values (tuple): A tuple containing the values to insert into the table.

        Returns:
            None

        Examples:
            # Inserting a new row into the 'users' table
            db_client._insert(
                table_name='users',
                columns=('username', 'email'),
                values=('john_doe', 'john_doe@example.com')
            )
        """
        try:
            sql_query = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))})"
            self.cursor.execute(sql_query, values)
            self.database_connection.commit()
        except (psycopg2.Error, IndexError) as error:
            log.error(
                '[class.%s] an error occurred while inserting a row into the table %s: %s\nColumns: %s\nValues: %s\nQuery: %s',
                __class__.__name__, table_name, error, columns, values, sql_query
            )

    def _select(
        self,
        table_name: str = None,
        columns: tuple = None,
        **kwargs
    ) -> Union[list, None]:
        """
        Selects data from a table in the database based on the given condition.

        Args:
            table_name (str): The name of the table to select data from.
            columns (tuple): A tuple containing the names of the columns to select.

        Keyword Args:
            condition (str): The condition to use to select the data.
            order_by (str): The column to use for ordering the data.
            limit (int): The maximum number of rows to return.

        Returns:
            list: A list of tuples containing the selected data.
                or
            None: If no data is found.

        Examples:
            >>> _select(table_name='users', columns=('username', 'email'), condition="id=1")
            [('john_doe', 'john_doe@exmaple.com')]
        """
        # base query
        sql_query = f"SELECT {', '.join(columns)} FROM {table_name}"
        if kwargs.get('condition', None):
            sql_query += f" WHERE {kwargs.get('condition')}"
        if kwargs.get('order_by', None):
            sql_query += f" ORDER BY {kwargs.get('order_by')}"
        if kwargs.get('limit', None):
            sql_query += f" LIMIT {kwargs.get('limit')}"
        self.cursor.execute(sql_query)
        return self.cursor.fetchall()

    def _update(
        self,
        table_name: str = None,
        values: str = None,
        condition: str = None
    ) -> None:
        """
        Update the specified table with the given values of values based on the specified condition.

        Args:
            table_name (str): The name of the table to update.
            values (str): The values of values to update in the table.
            condition (str): The condition to use for updating the table.

        Returns:
            None

        Examples:
            To update the 'users' table with a new username and password for a user with ID 1:
            >>> _update('users', "username='new_username', password='new_password'", "id=1")
        """
        self.cursor.execute(f"UPDATE {table_name} SET {values} WHERE {condition}")
        self.database_connection.commit()

    def _delete(
        self,
        table_name: str = None,
        condition: str = None
    ) -> None:
        """
        Delete rows from a table based on a condition.

        Args:
            table_name (str): The name of the table to delete rows from.
            condition (str): The condition to use to determine which rows to delete.

        Returns:
            None

        Examples:
            To delete all rows from the 'users' table where the 'username' column is 'john':
            >>> db._delete('users', "username='john'")
        """
        self.cursor.execute(f"DELETE FROM {table_name} WHERE {condition}")
        self.database_connection.commit()

    def add_message_to_queue(
        self,
        data: dict = None
    ) -> str:
        """
        Add a message to the queue table in the database.

        Args:
            data (dict): A dictionary containing the message details.

        Parameters:
            user_id (str): The user ID of the message sender.
            post_id (str): The ID of the post the message is related to.
            post_url (str): The URL of the post the message is related to.
            post_owner (str): The username of the post owner.
            link_type (str): The type of link in the message.
            message_id (str): The ID of the message.
            chat_id (str): The ID of the chat the message belongs to.
            scheduled_time (str): The time the message is scheduled to be sent.
            download_status (str): The status of the post downloading process.
            upload_status (str): The status of the post uploading process.

        Returns:
            str: A message indicating that the message was added to the queue.

        Examples:
            >>> data = {
            ...     'user_id': '12345',
            ...     'post_id': '67890',
            ...     'post_url': 'https://www.instagram.com/p/67890/',
            ...     'post_owner': 'johndoe',
            ...     'link_type': 'profile',
            ...     'message_id': 'abcde',
            ...     'chat_id': 'xyz',
            ...     'scheduled_time': '2022-01-01 12:00:00'
            ...     'download_status': 'not started',
            ...     'upload_status': 'not started'
            ... }
            >>> add_message_to_queue(message)
            'abcde: added to queue'
        """
        self._insert(
            table_name='queue',
            columns=(
                "user_id",
                "post_id",
                "post_url",
                "post_owner",
                "link_type",
                "message_id",
                "chat_id",
                "scheduled_time",
                "download_status",
                "upload_status"
            ),
            values=(
                data.get('user_id', None),
                data.get('post_id', None),
                data.get('post_url', None),
                data.get('post_owner', None),
                data.get('link_type', None),
                data.get('message_id', None),
                data.get('chat_id', None),
                data.get('scheduled_time', None),
                data.get('download_status', 'not started'),
                data.get('upload_status', 'not started'),
            )
        )
        return f"{data.get('message_id', None)}: added to queue"

    def get_message_from_queue(
        self,
        scheduled_time: str = None
    ) -> tuple:
        """
        Get a message from the queue table in the database.

        Args:
            scheduled_time (str): The time the message is scheduled to be sent.

        Returns:
            tuple: A tuple containing the message from the queue.

        Examples:
            >>> get_message_from_queue('2022-01-01 12:00:00')
            (1, '123456789', 'vahj5AN8aek', 'https://www.instagram.com/p/vahj5AN8aek', 'johndoe', 'post', '12345', '12346', '123456789',
            datetime.datetime(2023, 11, 14, 21, 21, 22, 603440), 'None', 'None', datetime.datetime(2023, 11, 14, 21, 14, 26, 680024), 'waiting')
        """
        message = self._select(
            table_name='queue',
            columns=("*",),
            condition=f"scheduled_time <= '{scheduled_time}' AND state IN ('waiting', 'processing')",
            limit=1
        )
        return message[0] if message else None

    def update_message_state_in_queue(
        self,
        post_id: str = None,
        state: str = None,
        **kwargs
    ) -> str:
        """
        Update the state of a message in the queue table and move it to the processed table if the state is 'processed'.

        Args:
            post_id (str): The ID of the post.
            state (str): The new state of the message.

        Keyword Args:
            download_status (str): The status of the post downloading process.
            upload_status (str): The status of the post uploading process.
            post_owner (str): The ID of the post owner.

        Parameters:
            table_name (str): The name of the table to update.
            values (str): The new value for the state column.
            condition (str): The condition to use to select the row to update.

        Returns:
            str: A response message indicating the status of the update.

        Examples:
            >>> update_message_state_in_queue(
                    post_id='123',
                    state='processed',
                    download_status='completed',
                    upload_status='completed',
                    post_owner='username123'
                )
            '456: processed'
        """
        values = f"state = '{state}'"

        if kwargs.get('post_owner'):
            values += f", post_owner = '{kwargs.get('post_owner')}'"
        if kwargs.get('download_status'):
            values += f", download_status = '{kwargs.get('download_status')}'"
        if kwargs.get('upload_status'):
            values += f", upload_status = '{kwargs.get('upload_status')}'"

        self._update(table_name='queue', values=values, condition=f"post_id = '{post_id}'")

        if state == 'processed':
            processed_message = self._select(
                table_name='queue',
                columns=("*",),
                condition=f"post_id = '{post_id}'",
                limit=1
            )
            self._insert(
                table_name='processed',
                columns=(
                    "user_id",
                    "post_id",
                    "post_url",
                    "post_owner",
                    "link_type",
                    "message_id",
                    "chat_id",
                    "download_status",
                    "upload_status",
                    "state"
                ),
                values=(
                    processed_message[0][1],
                    processed_message[0][2],
                    processed_message[0][3],
                    processed_message[0][4],
                    processed_message[0][5],
                    processed_message[0][6],
                    processed_message[0][7],
                    kwargs.get('download_status', 'pending'),
                    kwargs.get('upload_status', 'pending'),
                    state
                )
            )
            self._delete(table_name='queue', condition=f"post_id = '{post_id}'")
            response = f"{processed_message[0][6]}: processed"
        else:
            response = f"{post_id}: state updated"

        return response

    def verify_users_queue(self) -> None:
        """
        Verify the queue for all users and reschedule messages if necessary.
        If the message is not processed in time (for example, the bot was down), reschedule the message in the queue.

        Args:
            None

        Returns:
            None

        Examples:
            >>> verify_users_queue()
        """
        log.info("[class.%s]: verifying the queue for all users", __class__.__name__)
        users = self.users_list()
        for user in users:
            user_id = user[0]
            need_reschedule = False
            full_queue = self._select(
                table_name='queue',
                columns=("id", "scheduled_time"),
                condition=f"user_id = '{user_id}'",
                order_by='scheduled_time ASC',
                limit=1000
            )

            for message in full_queue:
                if message[1] < datetime.now() - timedelta(minutes=10):
                    need_reschedule = True
                    log.warning("[class.%s]: found a message in the queue that was not processed in time for user %s", __class__.__name__, user_id)
                    break

            if need_reschedule:
                log.warning("[class.%s]: rescheduling messages in the queue for user %s", __class__.__name__, user_id)
                # The lag between the current time and the scheduled time of the message
                minutes_lag = None
                # The difference in minutes between the current message and the previous message
                minutes_diff = None
                # The new scheduled time for the message after rescheduling
                new_schedule_time = None
                # Reschedule the all messages in the queue
                for message in full_queue:
                    minutes_lag = (datetime.now() - message[1]) / 60
                    if not new_schedule_time:
                        new_schedule_time = message[1] + minutes_lag
                        self._update(
                            table_name='queue',
                            values=f"scheduled_time = '{new_schedule_time}'",
                            condition=f"id = '{message[0]}'"
                        )
                    else:
                        minutes_diff = (message[1] + minutes_lag - new_schedule_time) / 60
                        # Add the difference in minutes between the current message and the previous message to the lag
                        minutes_skew = minutes_diff + minutes_lag
                        new_schedule_time = message[1] + minutes_skew
                        self._update(
                            table_name='queue',
                            values=f"scheduled_time = '{new_schedule_time}'",
                            condition=f"id = '{message[0]}'"
                        )
                    log.info("[class.%s]: rescheduled message %s: %s -> %s", __class__.__name__, message[0], message[1], new_schedule_time)
        log.info("[class.%s]: queue verification completed", __class__.__name__)

    def get_user_queue(
        self,
        user_id: str = None
    ) -> Union[dict, None]:
        """
        Get all messages from the queue table for the specified user.

        Args:
            user_id (str): The ID of the user.

        Returns:
            dict: A dictionary containing all messages from the queue for the specified user.

        Examples:
            >>> get_user_queue(user_id='12345')
            {
                '12345': [
                    {
                        'post_id': '123456789',
                        'scheduled_time': '2022-01-01 12:00:00'
                    }
                ]
            }
        """
        result = {}
        queue = self._select(
            table_name='queue',
            columns=("post_id", "scheduled_time"),
            condition=f"user_id = '{user_id}'",
            limit=1000
        )
        for message in queue:
            if user_id not in result:
                result[user_id] = []
            result[user_id].append({
                'post_id': message[0],
                'scheduled_time': message[1]
            })
        return result if result else None

    def get_user_processed(
        self,
        user_id: str = None
    ) -> Union[dict, None]:
        """
        Get last five messages from the processed table for the specified user.

        Args:
            user_id (str): The ID of the user.

        Returns:
            dict: A dictionary containing the last five messages from the processed table for the specified user.

        Examples:
            >>> get_user_processed(user_id='12345')
            {
                '12345': [
                    {
                        'post_id': '123456789',
                        'processed_time': '2022-01-01 12:00:00',
                        'state': 'completed'
                    }
                ]
            }
        """
        result = {}
        processed = self._select(
            table_name='processed',
            columns=("post_id", "timestamp", "state"),
            condition=f"user_id = '{user_id}'",
            order_by='timestamp DESC',
            limit=10
        )
        for message in processed:
            if user_id not in result:
                result[user_id] = []
            result[user_id].append({
                'post_id': message[0],
                'timestamp': message[1],
                'state': message[2]
            })
        return result if result else None

    def values_lock(
        self,
        lock_name: str = None
    ) -> str:
        """
        Set a lock in the database.

        Args:
            lock_name (str): The name of the lock to values.

        Returns:
            str: A message indicating that the lock has been values.

        Examples:
            >>> values_lock('example_lock')
            'example_lock: locked'
        """
        self._update(
            table_name='locks',
            values='enabled = TRUE',
            condition=f"name = '{lock_name}'"
        )
        return f"{lock_name}: locked"

    def revalues_lock(
        self,
        lock_name: str = None
    ) -> str:
        """
        Revaluess the lock with the given name by valuesting its 'enabled' field to False.

        Args:
            lock_name (str): The name of the lock to revalues.

        Returns:
            str: A message indicating that the lock has been unlocked.

        Examples:
            >>> revalues_lock('my_lock')
            'my_lock: unlocked'
        """
        self._update(
            table_name='locks',
            values='enabled = FALSE',
            condition=f"name = '{lock_name}'"
        )
        return f"{lock_name}: unlocked"

    def check_message_uniqueness(
        self,
        post_id: str = None,
        user_id: str = None
    ) -> bool:
        """
        Check if a message with the given post ID and chat ID already exists in the queue.

        Args:
            post_id (str): The ID of the post.
            user_id (str): The ID of the chat.

        Returns:
            bool: True if the message is unique, False otherwise.

        Examples:
            >>> check_message_uniqueness(post_id='12345', user_id='67890')
            True
        """
        queue = self._select(
            table_name='queue',
            columns=("id",),
            condition=f"post_id = '{post_id}' AND user_id = '{user_id}'",
            limit=1
        )
        processed = self._select(
            table_name='processed',
            columns=("id",),
            condition=f"post_id = '{post_id}' AND user_id = '{user_id}'",
            limit=1
        )

        if queue or processed:
            return False
        return True

    def keep_message(
        self,
        message_id: str = None,
        chat_id: str = None,
        message_type: str = None,
        message_content: Union[str, dict] = None,
        **kwargs
    ) -> str:
        """
        Add a message to the messages table in the database.

        Args:
            message_id (str): The ID of the message.
            chat_id (str): The ID of the chat.
            message_type (str): The type of the message.
            message_content (Union[str, dict]): The content of the message.

        Keyword Args:
            producer (str): The name of the producer of the message.

        Returns:
            str: A message indicating that the message was added to the messages table.

        Examples:
            >>> keep_message('12345', '67890', 'bot', 'status_message', 'Hello, username\n...')
            '12345 kept' or '12345 updated'
        """
        if kwargs.get('producer', None):
            producer = kwargs.get('producer')
        else:
            producer = 'bot'

        message_content_hash = get_hash(message_content)
        check_exist_message_type = self._select(
            table_name='messages',
            columns=("id", "message_id"),
            condition=f"message_type = '{message_type}' AND chat_id = '{chat_id}'",
        )
        if check_exist_message_type:
            self._update(
                table_name='messages',
                values=(
                    f"message_content_hash = '{message_content_hash}', "
                    f"message_id = '{message_id}', "
                    f"timestamp = CURRENT_TIMESTAMP"
                ),
                condition=f"id = '{check_exist_message_type[0][0]}'"
            )
            response = f"{message_id} updated"
        else:
            self._insert(
                table_name='messages',
                columns=("message_id", "chat_id", "message_type", "message_content_hash", "producer"),
                values=(message_id, chat_id, message_type, message_content_hash, producer)
            )
            response = f"{message_id} kept"
        return response

    def add_user(
        self,
        user_id: str = None,
        chat_id: str = None
    ) -> str:
        """
        Add a user to the users table in the database.

        Args:
            user_id (str): The ID of the user.
            chat_id (str): The ID of the chat.

        Returns:
            str: A message indicating that the user was added to the users table or that the user already exists.

        Examples:
            >>> add_user(user_id='12345', chat_id='67890')
            '12345 added'
                or
            '12345 already exists'
        """
        exist_user = self._select(table_name='users', columns=("user_id",), condition=f"user_id = '{user_id}'")
        if exist_user and user_id in exist_user[0]:
            result = f"{user_id} already exists"
        else:
            self._insert(
                table_name='users',
                columns=("chat_id", "user_id"),
                values=(chat_id, user_id)
            )
            result = f"{user_id} added"
        return result

    def users_list(self) -> list:
        """
        Get a list of all users in the database.

        Args:
            None

        Returns:
            list: A list of all users from the messages table.

        Examples:
            >>> users_list()
            # ('{user_id}', '{chat_id}')
            [('12345', '67890'), ('54321', '09876')]
        """
        users = self._select(
            table_name='users',
            columns=("user_id", "chat_id"),
            limit=1000
        )
        return users if users else None

    def get_considered_message(
        self,
        message_type: str = None,
        chat_id: str = None
    ) -> str:
        """
        Get a message with specified type and chat ID from the messages table in the database.

        Args:
            message_type (str): The type of the message.
            chat_id (str): The ID of the chat.

        Returns:
            tuple: A tuple containing the message from the messages table.

        Examples:
            >>> current_message_id(message_type='status_message', chat_id='12345')
            # ('message_id', 'chat_id', 'timestamp', 'message_content_hash')
            ('123456789', '12345', datetime.datetime(2023, 11, 14, 21, 14, 26, 680024), '2ef7bde608ce5404e97d5f042f95f89f1c232871d3d7')
        """
        message = self._select(
            table_name='messages',
            columns=("message_id", "chat_id", "timestamp", "message_content_hash",),
            condition=f"message_type = '{message_type}' AND chat_id = '{chat_id}'",
            limit=1
        )
        return message[0] if message else None
