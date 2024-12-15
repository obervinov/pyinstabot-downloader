"""This module contains a class for interacting with a PostgreSQL database using psycopg2"""
import os
import sys
import importlib
import json
import time
import psycopg2
from psycopg2 import pool
from logger import log
from .tools import get_hash


def reconnect_on_exception(method):
    """
    A decorator that catches the closed cursor exception and reconnects to the database.
    """
    def wrapper(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except psycopg2.Error as exception:
            log.warning('[Database]: Connection to the database was lost: %s. Attempting to reconnect...', str(exception))
            time.sleep(5)
            try:
                self.database_connections = self.create_connection_pool()
                log.info('[Database]: Reconnection successful.')
                return method(self, *args, **kwargs)
            except psycopg2.Error as inner_exception:
                log.error('[Database]: Failed to reconnect to the database: %s', str(inner_exception))
                raise inner_exception
    return wrapper


class DatabaseClient:
    """
    A class that represents a client for interacting with a PostgreSQL database.

    Attributes:
        database_connections (psycopg2.extensions.connection): A connection to the PostgreSQL database.
        vault (object): An object representing a HashiCorp Vault client for retrieving secrets.
        db_role (str): The role to use for generating database credentials.
        errors (psycopg2.errors): A collection of error classes for exceptions raised by the psycopg2 module.
        json (json): A JSON encoder and decoder for working with JSON data to execute database migrations.

    Methods:
        create_connection_pool(): Create a connection pool for the PostgreSQL database.
        get_connection(): Get a connection from the connection pool.
        close_connection(connection): Close the connection and return it to the connection pool.
        _prepare_db(): Prepare the database by creating and initializing the necessary tables.
        _migrations(): Execute database migrations to update the database schema or data.
        _is_migration_executed(migration_name): Check if a migration has already been executed.
        _mark_migration_as_executed(migration_name, version): Inserts a migration into the migrations table to mark it as executed.
        _create_table(table_name, columns): Create a new table in the database with the given name and columns if it does not already exist.
        _insert(table_name, columns, values): Inserts a new row into the specified table with the given columns and values.
        _select(table_name, columns, **kwargs): Selects rows from the specified table with the given columns based on the specified condition.
        _update(table_name, values, condition): Update the specified table with the given values of values based on the specified condition.
        _delete(table_name, condition): Delete rows from a table based on a condition.
        _reset_stale_records(): Reset stale records in the database. To ensure that the bot is restored after a restart.
        add_message_to_queue(data): Add a message to the queue table in the database.
        get_message_from_queue(scheduled_time): Get a one message from the queue table that is scheduled to be sent at the specified time.
        update_message_state_in_queue(post_id, state, **kwargs): Update the state of a message in the queue table and move it to the processed table
                                                                 if the state is 'processed'.
        update_schedule_time_in_queue(post_id, user_id, scheduled_time): Update the scheduled time of a message in the queue table.
        get_user_queue(user_id): Get messages from the queue table for the specified user.
        get_user_processed(user_id): Get last ten messages from the processed table for the specified user.
        check_message_uniqueness(post_id, user_id): Check if a message with the given post ID and chat ID already exists in the queue.
        keep_message(message_id, chat_id, message_content, **kwargs): Add a message to the messages table in the database.
        get_users(only_allowed): Get a list of users from the users table in the database.
        get_considered_message(message_type, chat_id): Get a message with specified type and chat ID from the messages table in the database.
        add_account_info(data): Add account information to the accounts table in the database.
        get_account_info(account_name): Get the account information from the accounts table in the database.

    Rises:
        psycopg2.Error: An error occurred while interacting with the PostgreSQL database.
    """
    def __init__(self, vault: object = None, db_role: str = None) -> None:
        """
        Initializes a new instance of the Database client.

        Args:
            vault (object): An object representing a HashiCorp Vault client for retrieving secrets with the database configuration.
            db_role (str): The role to use for generating database credentials.

        Examples:
            To create a new instance of the Database class:
            >>> from modules.database import Database
            >>> from modules.vault import Vault
            >>> vault = Vault()
            >>> db = Database(vault=vault)
        """
        self.json = json
        self.vault = vault
        self.db_role = db_role
        self.errors = psycopg2.errors
        self.database_connections = self.create_connection_pool()

        self._prepare_db()
        self._migrations()
        self._reset_stale_records()

    def create_connection_pool(self) -> pool.SimpleConnectionPool:
        """
        Create a connection pool for the PostgreSQL database.

        Returns:
            pool.SimpleConnectionPool: A connection pool for the PostgreSQL database.
        """
        required_keys_configuration = {"host", "port", "dbname", "connections"}
        required_keys_credentials = {"username", "password"}
        db_configuration = self.vault.kv2engine.read_secret(path='configuration/database')
        db_credentials = self.vault.dbengine.generate_credentials(role=self.db_role)

        if not db_configuration or not db_credentials:
            raise ValueError('Database configuration or credentials are missing')

        missing_keys = (required_keys_configuration - set(db_configuration.keys())) | (required_keys_credentials - set(db_credentials.keys()))
        if missing_keys:
            raise KeyError("Missing keys in the database configuration or credentials: {missing_keys}")

        log.info(
            '[Database]: Creating a connection pool for the %s:%s/%s',
            db_configuration['host'], db_configuration['port'], db_configuration['dbname']
        )
        settings = {
            'minconn': 1, 'maxconn': db_configuration['connections'], 'host': db_configuration['host'], 'port': db_configuration['port'],
            'user': db_credentials['username'], 'password': db_credentials['password'], 'database': db_configuration['dbname']
        }
        return pool.SimpleConnectionPool(**settings)

    def get_connection(self) -> psycopg2.extensions.connection:
        """
        Get a connection from the connection pool.

        Returns:
            psycopg2.extensions.connection: A connection to the PostgreSQL database.
        """
        return self.database_connections.getconn()

    def close_connection(self, connection: psycopg2.extensions.connection) -> None:
        """
        Close the cursor and return it to the connection pool.

        Args:
            connection (psycopg2.extensions.connection): A connection to the PostgreSQL database.
        """
        self.database_connections.putconn(connection)

    def _prepare_db(self) -> None:
        """
        Prepare the database by creating and initializing the necessary tables.
        """
        # Read configuration file for database initialization
        configuration_path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '../configs/databases.json'))
        with open(configuration_path, encoding='UTF-8') as config_file:
            database_init_configuration = json.load(config_file)

        # Create databases if does not exist
        for table in database_init_configuration.get('Tables', None):
            self._create_table(table_name=table['name'], columns="".join(f"{column}" for column in table['columns']))
            log.info('[Database]: Prepare Database: create table `%s` (if does not exist)', table['name'])

        # Write necessary data to the database (service records)
        if database_init_configuration.get('DataSeeding', None):
            # ! This code block needs to be improved after some service data will appear for filling,
            # ! because this code creates duplicate lines each time the project is started.
            for data in database_init_configuration['DataSeeding']:
                self._insert(table_name=data['table'], columns=tuple(data['data'].keys()), values=tuple(data['data'].values()))
                log.info('[Database]: Prepare Database: data seeding has been added to the `%s` table', data['table'])

    def _migrations(self) -> None:
        """
        Execute database migrations to update the database schema or data.
        """
        log.info('[Database]: Migrations: Preparing to execute database migrations...')
        # Migrations directory
        migrations_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../migrations'))
        sys.path.append(migrations_dir)
        migration_files = [f for f in os.listdir(migrations_dir) if f.endswith('.py')]
        migration_files.sort()

        for migration_file in migration_files:
            if migration_file.endswith('.py'):
                migration_module_name = migration_file[:-3]

                if not self._is_migration_executed(migration_name=migration_module_name):
                    log.info('[Database]: Migrations: executing the %s migration...', migration_module_name)
                    migration_module = importlib.import_module(name=migration_module_name)
                    migration_module.execute(self)
                    version = getattr(migration_module, 'VERSION', migration_module_name)
                    self._mark_migration_as_executed(migration_name=migration_module_name, version=version)
                else:
                    log.info('[Database] Migrations: the %s has already been executed and was skipped', migration_module_name)
            else:
                log.error('[Database]: Migrations: the %s is not a valid migration file', migration_file)

    def _is_migration_executed(self, migration_name: str = None) -> bool:
        """
        Check if a migration has already been executed.

        Args:
            migration_name (str): The name of the migration to check.

        Returns:
            bool: True if the migration has been executed, False otherwise.
        """
        return self._select(table_name='migrations', columns=('id',), condition=f"name = '{migration_name}'")

    def _mark_migration_as_executed(self, migration_name: str = None, version: str = None) -> None:
        """
        Inserts a migration into the migrations table to mark it as executed.

        Args:
            migration_name (str): The name of the migration to mark as executed.
        """
        self._insert(table_name='migrations', columns=('name', 'version'), values=(migration_name, version))

    def _create_table(self, table_name: str = None, columns: str = None) -> None:
        """
        Create a new table in the database with the given name and columns if it does not already exist.

        Args:
            table_name (str): The name of the table to create.
            columns (str): A string containing the column definitions for the table.

        Examples:
            To create a new table called 'users' with columns 'id' and 'name', you can call the method like this:
            >>> _create_table('users', 'id INTEGER PRIMARY KEY, name TEXT')
        """
        conn = self.get_connection()
        with conn.cursor() as cursor:
            cursor.execute(f"CREATE TABLE IF NOT EXISTS {table_name} ({columns})")
        conn.commit()
        self.close_connection(conn)

    @reconnect_on_exception
    def _insert(self, table_name: str = None, columns: tuple = None, values: tuple = None) -> None:
        """
        Inserts a new row into the specified table with the given columns and values.

        Args:
            table_name (str): The name of the table to insert the row into.
            columns (tuple): A tuple containing the names of the columns to insert the values into.
            values (tuple): A tuple containing the values to insert into the table.

        Examples:
            >>> db_client._insert(
            ...   table_name='users',
            ...   columns=('username', 'email'),
            ...   values=('john_doe', 'john_doe@example.com')
            ... )
        """
        try:
            sql_query = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))})"
            conn = self.get_connection()
            with conn.cursor() as cursor:
                cursor.execute(sql_query, values)
            conn.commit()
            self.close_connection(conn)
        except IndexError as error:
            log.error(
                '[Database]: An error occurred while inserting a row into the table %s: %s\nColumns: %s\nValues: %s\nQuery: %s',
                table_name, error, columns, values, sql_query
            )
        except TypeError as error:
            log.error(
                '[Database]: Wrong data type in the columns or values: %s\nColumns: %s\nValues: %s\nQuery: %s',
                error, columns, values, sql_query
            )
        except psycopg2.Error as error:
            log.error(
                '[Database]: A database-related error occurred: %s\nColumns: %s\nValues: %s\nQuery: %s',
                error, columns, values, sql_query
            )

    @reconnect_on_exception
    def _select(self, table_name: str = None, columns: tuple = None, **kwargs) -> list | None:
        """
        Selects rows from the specified table with the given columns based on the specified condition.

        Args:
            table_name (str): The name of the table to select data from.
            columns (tuple): A tuple containing the names of the columns to select.

        Keyword Args:
            condition (str): The condition to use to select the data.
            order_by (str): The column to use for ordering the data.
            limit (int): The maximum number of rows to return.

        Returns:
            list: a list of tuples containing the selected data.
                or
            None: if no data is found.

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

        conn = self.get_connection()
        with conn.cursor() as cursor:
            cursor.execute(sql_query)
            response = cursor.fetchall()
        self.close_connection(conn)
        return response if response else None

    @reconnect_on_exception
    def _update(self, table_name: str = None, values: str = None, condition: str = None) -> None:
        """
        Update the specified table with the given values of values based on the specified condition.

        Args:
            table_name (str): The name of the table to update.
            values (str): The values of values to update in the table.
            condition (str): The condition to use for updating the table.

        Examples:
            >>> _update('users', "username='new_username', password='new_password'", "id=1")
        """
        conn = self.get_connection()
        with conn.cursor() as cursor:
            cursor.execute(f"UPDATE {table_name} SET {values} WHERE {condition}")
        conn.commit()
        self.close_connection(conn)

    @reconnect_on_exception
    def _delete(self, table_name: str = None, condition: str = None) -> None:
        """
        Delete rows from a table based on a condition.

        Args:
            table_name (str): The name of the table to delete rows from.
            condition (str): The condition to use to determine which rows to delete.

        Examples:
            To delete all rows from the 'users' table where the 'username' column is 'john':
            >>> db._delete('users', "username='john'")
        """
        conn = self.get_connection()
        with conn.cursor() as cursor:
            cursor.execute(f"DELETE FROM {table_name} WHERE {condition}")
        conn.commit()
        self.close_connection(conn)

    def _reset_stale_records(self) -> None:
        """
        Reset stale records in the database. To ensure that the bot is restored after a restart.
        More: https://github.com/obervinov/pyinstabot-downloader/issues/84
        """
        # Reset stale status_message (can be only one status_message per chat)
        log.info('[Database]: Resetting stale status messages...')
        status_messages = self._select(table_name='messages', columns=("id", "state"), condition="message_type = 'status_message'")
        if status_messages:
            for message in status_messages:
                if message[1] != 'updated':
                    self._update(table_name='messages', values="state = 'updated'", condition=f"id = '{message[0]}'")
                    log.info('[Database]: Stale status messages have been reset')
                else:
                    log.info('[Database]: No stale status messages found')

    def add_message_to_queue(self, data: dict = None) -> str:
        """
        Add a message to the queue table in the database.

        Args:
            data (dict): A dictionary containing the message details.

        Parameters:
            user_id (str): The user ID of the message sender.
            post_id (str): The ID of the post the message is related to.
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
            ...     'post_owner': 'johndoe',
            ...     'link_type': 'profile',
            ...     'message_id': 'abcde',
            ...     'chat_id': 'xyz',
            ...     'scheduled_time': '2022-01-01 12:00:00',
            ...     'download_status': 'not started',
            ...     'upload_status': 'not started'
            ... }
            >>> database.add_message_to_queue(data=data)
            'abcde: added to queue'
        """
        self._insert(
            table_name='queue',
            columns=(
                "user_id", "post_id", "post_url", "post_owner", "link_type",
                "message_id", "chat_id", "scheduled_time", "download_status", "upload_status"
            ),
            values=(
                data.get('user_id', None), data.get('post_id', None), f"https://www.instagram.com/p/{data.get('post_id', None)}",
                data.get('post_owner', None), data.get('link_type', None), data.get('message_id', None), data.get('chat_id', None),
                data.get('scheduled_time', None), data.get('download_status', 'not started'), data.get('upload_status', 'not started')
            )
        )
        return f"{data.get('message_id', None)}: added to queue"

    def get_message_from_queue(self, scheduled_time: str = None) -> tuple:
        """
        Get a one message from the queue table that is scheduled to be sent at the specified time.
        The message will be returned before or equal to the specified timestamp in the argument.

        Args:
            scheduled_time (str): The time at which the message is scheduled to be sent.

        Returns:
            tuple: A tuple containing the message from the queue.

        Examples:
            >>> database.get_message_from_queue('2022-01-01 12:00:00')
            (1, '123456789', 'vahj5AN8aek', 'https://www.example.com/p/vahj5AN8aek', 'johndoe', 'post', '12345', '12346', '123456789',
            datetime.datetime(2023, 11, 14, 21, 21, 22, 603440), 'None', 'None', datetime.datetime(2023, 11, 14, 21, 14, 26, 680024), 'waiting')
        """
        message = self._select(
            table_name='queue', columns=("*"), condition=f"scheduled_time <= '{scheduled_time}' AND state IN ('waiting', 'processing')", limit=1
        )
        return message[0] if message else None

    def update_message_state_in_queue(self, post_id: str = None, state: str = None, **kwargs) -> str:
        """
        Update the state of a message in the queue table and move it to the processed table if the state is 'processed'.

        Args:
            post_id (str): The ID of the post.
            state (str): The new state of the message.

        Keyword Arguments:
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
            >>> database.update_message_state_in_queue(
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
            processed_message = self._select(table_name='queue', columns=("*"), condition=f"post_id = '{post_id}'", limit=1)
            self._insert(
                table_name='processed',
                columns=(
                    "user_id", "post_id", "post_url", "post_owner", "link_type", "message_id", "chat_id", "download_status", "upload_status", "state"
                ),
                values=(
                    processed_message[0][1], processed_message[0][2], processed_message[0][3], processed_message[0][4],
                    processed_message[0][5], processed_message[0][6], processed_message[0][7],
                    kwargs.get('download_status', 'pending'), kwargs.get('upload_status', 'pending'), state
                )
            )
            self._delete(table_name='queue', condition=f"post_id = '{post_id}'")
            response = f"{processed_message[0][6]}: processed"
        else:
            response = f"{post_id}: state updated"

        return response

    def update_schedule_time_in_queue(self, post_id: str = None, user_id: str = None, scheduled_time: str = None) -> str:
        """
        Update the scheduled time of a message in the queue table.

        Args:
            post_id (str): The ID of the post.
            user_id (str): The ID of the user.
            scheduled_time (str): The new scheduled time for the message.

        Returns:
            str: A response message indicating the status of the update.

        Examples:
            >>> update_schedule_time_in_queue(post_id='123', user_id='12345', scheduled_time='2022-01-01 12:00:00')
            '123: scheduled time updated'
        """
        self._update(table_name='queue', values=f"scheduled_time = '{scheduled_time}'", condition=f"post_id = '{post_id}' AND user_id = '{user_id}'")
        return f"{post_id}: scheduled time updated"

    def get_user_queue(self, user_id: str = None) -> dict:
        """
        Get messages from the queue table for the specified user.

        Args:
            user_id (str): The ID of the user.

        Returns:
            dict: A list of dictionaries containing the messages from the queue table for the specified user.

        Examples:
            >>> get_user_queue(user_id='12345')
            [{'post_id': '123456789', 'scheduled_time': '2022-01-01 12:00:00'}]
        """
        result = []
        queue = self._select(
            table_name='queue', columns=("post_id", "scheduled_time"), condition=f"user_id = '{user_id}'", order_by='scheduled_time ASC', limit=10000
        )
        if queue:
            for message in queue:
                result.append({'post_id': message[0], 'scheduled_time': message[1]})
        return result

    def get_user_processed(self, user_id: str = None) -> dict:
        """
        Get last ten messages from the processed table for the specified user.
        It is used to display the last messages sent by the bot to the user.

        Args:
            user_id (str): The ID of the user.

        Returns:
            dict: A list of dictionaries containing the last ten messages from the processed table for the specified user.

        Examples:
            >>> get_user_processed(user_id='12345')
            [{'post_id': '123456789', 'timestamp': '2022-01-01 12:00:00', 'state': 'processed'}]
        """
        result = []
        processed = self._select(
            table_name='processed', columns=("post_id", "timestamp", "state"),
            condition=f"user_id = '{user_id}'", order_by='timestamp ASC', limit=10000
        )
        if processed:
            for message in processed:
                result.append({'post_id': message[0], 'timestamp': message[1], 'state': message[2]})
        return result

    def check_message_uniqueness(self, post_id: str = None, user_id: str = None) -> bool:
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
        queue = self._select(table_name='queue', columns=("id",), condition=f"post_id = '{post_id}' AND user_id = '{user_id}'", limit=1)
        processed = self._select(table_name='processed', columns=("id",), condition=f"post_id = '{post_id}' AND user_id = '{user_id}'", limit=1)
        if queue or processed:
            return False
        return True

    def keep_message(self, message_id: str = None, chat_id: str = None, message_content: str | dict = None, **kwargs) -> str:
        """
        Add a message to the messages table in the database.
        It is used to store the last message sent to the user for updating the message in the future.

        Args:
            message_id (str): The ID of the message.
            chat_id (str): The ID of the chat.
            message_content (str | dict): The content of the message.

        Keyword Args:
            message_type (str): The type of the message.
            state (str): The state of the message.
            recreated (bool): A flag indicating whether the message was recreated.

        Returns:
            str: A message indicating that the message was added to the messages table.

        Examples:
            >>> keep_message('12345', '67890', 'Hello, World!', message_type='status_message', state='updated')
            '12345 kept' or '12345 updated'
        """
        message_type = kwargs.get('message_type', None)
        state = kwargs.get('state', 'updated')
        recreated = kwargs.get('recreated', False)
        message_content_hash = get_hash(message_content)
        check_exist_message_type = self._select(
            table_name='messages', columns=("id", "message_id"), condition=f"message_type = '{message_type}' AND chat_id = '{chat_id}'"
        )
        response = None

        if check_exist_message_type and recreated:
            self._update(
                table_name='messages',
                values=(
                    f"message_content_hash = '{message_content_hash}', message_id = '{message_id}', "
                    f"state = '{state}', updated_at = CURRENT_TIMESTAMP, created_at = CURRENT_TIMESTAMP"
                ),
                condition=f"id = '{check_exist_message_type[0][0]}'"
            )
            response = f"{message_id} recreated"

        elif check_exist_message_type and not recreated:
            self._update(
                table_name='messages',
                values=(
                    f"message_content_hash = '{message_content_hash}', message_id = '{message_id}', state = '{state}', updated_at = CURRENT_TIMESTAMP"
                ),
                condition=f"id = '{check_exist_message_type[0][0]}'"
            )
            response = f"{message_id} updated"

        elif not check_exist_message_type:
            self._insert(
                table_name='messages',
                columns=("message_id", "chat_id", "message_type", "message_content_hash", "producer"),
                values=(message_id, chat_id, message_type, message_content_hash, 'bot')
            )
            response = f"{message_id} kept"

        else:
            log.warning('[Database]: Message with ID %s already exists in the messages table and cannot be updated', message_id)
            response = f"{message_id} already exists"

        return response

    def get_users(self, only_allowed: bool = True) -> dict:
        """
        This method will be deprecated after https://github.com/obervinov/users-package/issues/44 (users-package:v3.1.0).
        Get a dictionary of all users with their metadata from the users table in the database.
        By default, the method returns only allowed users.

        Args:
            only_allowed (bool): A flag indicating whether to return only allowed users. Default is True.

        Returns:
            dict: A dictionary containing all users in the database and their metadata.

        Examples:
            >>> get_users()
            [{'user_id': '12345', 'chat_id': '67890', 'status': 'denied'}, {'user_id': '12346', 'chat_id': '67891', 'status': 'allowed'}]
        """
        users_dict = []
        if only_allowed:
            users = self._select(table_name='users', columns=("user_id", "chat_id", "status"), condition="status = 'allowed'", limit=1000)
        else:
            users = self._select(table_name='users', columns=("user_id", "chat_id", "status"), limit=1000)

        if users:
            for user in users:
                users_dict.append({'user_id': user[0], 'chat_id': user[1], 'status': user[2]})
        return users_dict

    def get_considered_message(self, message_type: str = None, chat_id: str = None) -> tuple:
        """
        Get a message with specified type and chat ID from the messages table in the database.

        Args:
            message_type (str): The type of the message.
            chat_id (str): The ID of the chat.

        Returns:
            tuple: A tuple containing the message from the messages table.

        Examples:
            >>> current_message_id(message_type='status_message', chat_id='12345')
            # ('message_id', 'chat_id', 'created_at', 'updated_at', 'message_content_hash', 'state')
            ('123456789', '12345', datetime.datetime, datetime.datetime, 'hash', 'updated')
        """
        message = self._select(
            table_name='messages',
            columns=("message_id", "chat_id", "created_at", "updated_at", "message_content_hash", "state"),
            condition=f"message_type = '{message_type}' AND chat_id = '{chat_id}'",
            limit=1
        )
        return message[0] if message else None

    def add_account_info(self, data: dict = None) -> None:
        """
        Add account information to the accounts table in the database.

        Args:
            data (dict): A dictionary containing the account details.

        Parameters:
            username (str): The username of the account.
            pk (int): The primary key of the account.
            full_name (str): The full name of the account.
            media_count (int): The number of media items in the account.
            follower_count (int): The number of followers of the account.
            following_count (int): The number of accounts the account is following.
            cursor (str): The cursor for the account.
        """
        exist_account = self._select(table_name='accounts', columns=("id",), condition=f"username = '{data.get('username')}'")

        if exist_account:
            self._update(
                table_name='accounts',
                values={f"{key} = '{value}'" for key, value in data.items()},
                condition=f"id = '{exist_account[0][0]}'"
            )
        else:
            self._insert(table_name='accounts', columns=data.keys(), values=data.values())

    def get_account_info(self, username: str = None) -> tuple:
        """
        Get the account information from the accounts table in the database.

        Args:
            username (str): The username of the account.

        Returns:
            tuple: A tuple containing the account information from the accounts table.
                pk (int): The primary key of the account.
                cursor (str): The cursor for the account.
        """
        account = self._select(table_name='accounts', columns=("pk", "cursor"), condition=f"username = '{username}'", limit=1)
        return account[0] if account else None
