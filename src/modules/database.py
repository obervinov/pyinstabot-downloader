"""This module contains a class for interacting with a PostgreSQL database using psycopg2."""

import os
import sys
import importlib
from typing import Union
import psycopg2
from logger import log


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
            db_configuration = vault.read_secret(
                path=f"configuration/database-{environment}"
            )
        else:
            db_configuration = vault.read_secret(
                path='configuration/database'
            )
        log.info(
            '[class.%s] Initializing database connection to %s:%s',
            __class__.__name__,
            db_configuration['host'],
            db_configuration['port']
        )

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
        # Create a table for the message queue
        # Messages received by the bot are placed in this table for further processing
        # at the specified time by a separate thread
        log.info(
            '[class.%s] Preparing database: table \'queue\'...',
            __class__.__name__
        )
        self._create_table(
            table_name='queue',
            columns=(
                'id SERIAL PRIMARY KEY, '
                'user_id VARCHAR(255) NOT NULL, '
                'post_id VARCHAR(255) NOT NULL, '
                'post_url VARCHAR(255) NOT NULL, '
                'post_owner VARCHAR(255) NOT NULL, '
                'link_type VARCHAR(255) NOT NULL DEFAULT \'post\', '
                'message_id VARCHAR(255) NOT NULL, '
                'response_message_id VARCHAR(255) NOT NULL, '
                'chat_id VARCHAR(255) NOT NULL, '
                'scheduled_time TIMESTAMP NOT NULL, '
                'download_status VARCHAR(255) NOT NULL DEFAULT \'not started\', '
                'upload_status VARCHAR(255) NOT NULL DEFAULT \'not started\', '
                'timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, '
                'state VARCHAR(255) NOT NULL DEFAULT \'waiting\''
            )
        )
        # Create a table for the message processed
        # After processing from the queue, the record should be moved to this table
        # and enriched with additional data
        log.info(
            '[class.%s] Preparing database: table \'processed\'...',
            __class__.__name__
        )
        self._create_table(
            table_name='processed',
            columns=(
                'id SERIAL PRIMARY KEY, '
                'user_id VARCHAR(255) NOT NULL, '
                'post_id VARCHAR(255) NOT NULL, '
                'post_url VARCHAR(255) NOT NULL, '
                'post_owner VARCHAR(255) NOT NULL, '
                'link_type VARCHAR(255) NOT NULL DEFAULT \'post\', '
                'message_id VARCHAR(255) NOT NULL, '
                'chat_id VARCHAR(255) NOT NULL, '
                'download_status VARCHAR(255) NOT NULL, '
                'upload_status VARCHAR(255) NOT NULL, '
                'timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, '
                'state VARCHAR(255) NOT NULL DEFAULT \'processed\''
            )
        )
        # Create a table for service migrations when updating the service
        # The table stores the name of the migration and its version
        log.info(
            '[class.%s] Preparing database: table \'migrations\'...',
            __class__.__name__
        )
        self._create_table(
            table_name='migrations',
            columns=(
                'id SERIAL PRIMARY KEY, '
                'name VARCHAR(255) NOT NULL,'
                'version VARCHAR(255) NOT NULL, '
                'timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP'
            )
        )
        # Create a table for blocking exceptions (locks)
        # This table will record the locks caused by various exceptions when the bot is running.
        # These locks will block various bot functionality until manual intervention.
        log.info(
            '[class.%s] Preparing database: table \'locks\'...',
            __class__.__name__
        )
        self._create_table(
            table_name='locks',
            columns=(
                'id SERIAL PRIMARY KEY, '
                'name VARCHAR(255) NOT NULL,'
                'behavior VARCHAR(255) NOT NULL, '
                'enabled BOOLEAN NOT NULL DEFAULT FALSE, '
                'description VARCHAR(255) NOT NULL, '
                'caused_by VARCHAR(255) NOT NULL, '
                'tip VARCHAR(255) NOT NULL, '
                'timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP'
            )
        )
        # Add kind of locks to the table
        # The table stores the name of the lock and its description
        log.info(
            '[class.%s] Preparing database: add system records to table \'locks\'...',
            __class__.__name__
        )
        # Dictionary of locks for the table
        locks = [
            {
                'id': 1,
                'name': 'Unauthorized',
                'behavior': 'block:downloader_class',
                'description': 'Locks the post downloading functionality',
                'caused_by': '401:unauthorized',
                'tip': 'Instagram session expired, invalid credentials or account is blocked'
            },
            {
                'id': 2,
                'name': 'BadRequest',
                'behavior': 'block:downloader_class:post_link',
                'description': 'Locks the specified post downloading functionality',
                'caused_by': '400:badrequest',
                'tip': 'When trying to upload content, an error occurs with an invalid request'
            }
        ]
        table_name = 'locks'
        columns = 'id, name, behavior, description, caused_by, tip'
        for lock in locks:
            check_exist_lock = self._select(
                table_name=table_name,
                columns=columns,
                condition=f"name = '{lock['name']}'"
            )
            if not check_exist_lock:
                self._insert(
                    table_name=table_name,
                    columns=columns,
                    values=(
                        f"'{lock['id']}', "
                        f"'{lock['name']}', "
                        f"'{lock['behavior']}', "
                        f"'{lock['description']}', "
                        f"'{lock['caused_by']}', "
                        f"'{lock['tip']}'"
                    )
                )
            else:
                log.info(
                    '[class.%s] The lock %s has already been added to the table %s and was skipped',
                    __class__.__name__,
                    lock['name'],
                    table_name
                )
        # Create a table to keep track of the bot's messages
        # The table stores the message ID and the chat ID
        log.info(
            '[class.%s] Preparing database: table \'messages\'...',
            __class__.__name__
        )
        self._create_table(
            table_name='messages',
            columns=(
                'id SERIAL PRIMARY KEY, '
                'message_id VARCHAR(255) NOT NULL, '
                'chat_id VARCHAR(255) NOT NULL, '
                'timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, '
                'message_type VARCHAR(255) NOT NULL , '
                'producer VARCHAR(255) NOT NULL'
            )
        )
        # Create a table to keep users in the database
        # The table stores the chat ID, the user ID
        log.info(
            '[class.%s] Preparing database: table \'users\'...',
            __class__.__name__
        )
        self._create_table(
            table_name='users',
            columns=(
                'id SERIAL PRIMARY KEY, '
                'chat_id VARCHAR(255) NOT NULL, '
                'user_id VARCHAR(255) NOT NULL'
            )
        )

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
        log.info(
            '[class.%s] Reading database migrations...',
            __class__.__name__
        )
        sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../migrations')))
        migrations_dir = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                '../migrations'
            )
        )

        for migration_file in os.listdir(migrations_dir):
            log.info(
                '[class.%s] Executing migration: %s...',
                __class__.__name__,
                migration_file
            )
            if migration_file.endswith('.py'):
                migration_module_name = migration_file[:-3]

                if not self._is_migration_executed(migration_module_name):
                    migration_module = importlib.import_module(migration_module_name)
                    migration_module.execute(self)
                    version = getattr(migration_module, 'VERSION', migration_module_name)
                    self._mark_migration_as_executed(migration_module_name, version)
                else:
                    log.info(
                        '[class.%s] the %s migration has already been executed and was skipped',
                        __class__.__name__,
                        migration_module_name
                    )

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
        self.cursor.execute(
            f"SELECT id FROM migrations WHERE name = '{migration_name}'"
        )
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
        self.cursor.execute(
            f"INSERT INTO migrations (name, version) VALUES ('{migration_name}', '{version}')"
        )
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
        columns: str = None,
        values: str = None
    ) -> None:
        """
        Inserts a new row into the specified table with the given columns and values.

        Args:
            table_name (str): The name of the table to insert the row into.
            columns (str): A comma-separated string of column names to insert values into.
            values (str): A comma-separated string of values to insert into the specified columns.

        Returns:
            None

        Examples:
            To insert a new row into the 'users' table with the columns 'name' and 'age' and the values 'John' and 30:
            _insert('users', 'name, age', "'John', 30")
        """
        self.cursor.execute(f"INSERT INTO {table_name} ({columns}) VALUES ({values})")
        self.database_connection.commit()

    # pylint: disable=too-many-arguments
    def _select(
        self,
        table_name: str = None,
        columns: str = None,
        condition: str = None,
        order_by: str = None,
        limit: int = 1
    ) -> Union[list, None]:
        """
        Selects data from a table in the database based on the given condition.

        Args:
            table_name (str): The name of the table to select data from.
            columns (str): The columns to select data from.
            condition (str): The condition to filter the data by.
            order_by (str): The column to order the data by.
            limit (int): The maximum number of rows to return.

        Returns:
            list: A list of tuples containing the selected data.
                or
            None: If no data is found.

        Examples:
            >>> db = Database()
            >>> db._select("users", "username, email", "age > 18")
            [('john_doe', 'john_doe@example.com'), ('jane_doe', 'jane_doe@example.com')]
        """
        # base query
        sql_query = f"SELECT {columns} FROM {table_name}"
        if condition:
            sql_query += f" WHERE {condition}"
        if order_by:
            sql_query += f" ORDER BY {order_by}"
        sql_query += f" LIMIT {limit}"
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

    def _close(self) -> None:
        """
        Close the database connection.

        Args:
            None

        Parameters:
            None

        Returns:
            None

        Examples:
            _close()
        """
        self.database_connection.close()

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
                'user_id, '
                'post_id, '
                'post_url, '
                'post_owner, '
                'link_type, '
                'message_id, '
                'response_message_id, '
                'chat_id, '
                'scheduled_time, '
                'download_status, '
                'upload_status'
            ),
            values=(
                f"'{data.get('user_id', None)}', "
                f"'{data.get('post_id', None)}', "
                f"'{data.get('post_url', None)}', "
                f"'{data.get('post_owner', None)}', "
                f"'{data.get('link_type', None)}', "
                f"'{data.get('message_id', None)}', "
                f"'{data.get('response_message_id', None)}', "
                f"'{data.get('chat_id', None)}', "
                f"'{data.get('scheduled_time', None)}',"
                f"'{data.get('download_status', None)}', "
                f"'{data.get('upload_status', None)}'"
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
            columns='*',
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
            **kwargs: Additional keyword arguments.

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
                    upload_status='completed'
                )
            '456: processed'
        """
        self._update(
            table_name='queue',
            values=f"state = '{state}'",
            condition=f"post_id = '{post_id}'"
        )

        if state == 'processed':
            processed_message = self._select(
                table_name='queue',
                columns='*',
                condition=f"post_id = '{post_id}'",
                limit=1
            )
            self._insert(
                table_name='processed',
                columns='user_id, post_id, post_url, post_owner, link_type, message_id, chat_id, download_status, upload_status, state',
                values=(
                    f"'{processed_message[0][1]}', "
                    f"'{processed_message[0][2]}', "
                    f"'{processed_message[0][3]}', "
                    f"'{processed_message[0][4]}', "
                    f"'{processed_message[0][5]}', "
                    f"'{processed_message[0][6]}', "
                    f"'{processed_message[0][7]}', "
                    f"'{kwargs.get('download_status', 'pending')}', "
                    f"'{kwargs.get('upload_status', 'pending')}', "
                    f"'{state}'"
                )
            )
            self._delete(
                table_name='queue',
                condition=f"post_id = '{post_id}'"
            )
            response = f"{processed_message[0][6]}: processed"
        else:
            response = f"{post_id}: state updated"

        return response

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
            columns='post_id, scheduled_time',
            condition=f"user_id = '{user_id}'",
            limit=100
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
            columns='post_id, timestamp, state',
            condition=f"user_id = '{user_id}'",
            order_by='timestamp DESC',
            limit=5
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
            columns='id',
            condition=f"post_id = '{post_id}' AND user_id = '{user_id}'",
            limit=1
        )
        processed = self._select(
            table_name='processed',
            columns='id',
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
        producer: str = 'bot',
        message_type: str = None
    ) -> str:
        """
        Add a message to the messages table in the database.

        Args:
            message_id (str): The ID of the message.
            chat_id (str): The ID of the chat.
            producer (str): The name of the producer of the message.
            message_type (str): The type of the message.

        Returns:
            str: A message indicating that the message was added to the messages table.

        Examples:
            >>> keep_message('12345', '67890', 'bot', 'status_message')
            '12345 kept'
        """
        self._insert(
            table_name='messages',
            columns='message_id, chat_id, message_type, producer',
            values=f"'{message_id}', '{chat_id}', '{message_type}', '{producer}'"
        )
        return f"{message_id} kept"

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
            >>> add_user('12345')
            '12345 added'
        """
        if user_id in self._select(
            table_name='users',
            columns='user_id',
            condition=f"user_id = '{user_id}'"
        ):
            return f"{user_id} already exists"
        self._insert(
            table_name='users',
            columns='chat_id, user_id',
            values=f"'{chat_id}', '{user_id}'"
        )
        return f"{user_id} added"

    def users_list(
        self
    ) -> list:
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
            columns='user_id, chat_id',
        )
        return users if users else None

    def get_current_message_id(
        self,
        message_type: str = None,
        chat_id: str = None
    ) -> str:
        """
        Get the current message ID for the specified type.

        Args:
            message_type (str): The type of the message.
            chat_id (str): The ID of the chat.

        Returns:
            str: The current message ID for the specified type.

        Examples:
            >>> current_message_id('status_message', chat_id='12345')
            ('123456789', '2022-01-01 12:00:00')
        """
        message = self._select(
            table_name='messages',
            columns='message_id, timestamp',
            condition=f"message_type = '{message_type}' AND chat_id = '{chat_id}'",
            order_by='timestamp DESC',
            limit=1
        )
        return message[0] if message else None
