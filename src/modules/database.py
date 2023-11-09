"""This module contains a class for interacting with a PostgreSQL database using psycopg2."""

import os
import importlib
import psycopg2


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
        vault: object = None
    ):
        """
        Initializes a new instance of the Database class.

        Args:
            vault (object): An instance of the Vault class.

        Parameters:
            host (str): The hostname of the database server.
            port (int): The port number of the database server.
            user (str): The username to use when connecting to the database.
            password (str): The password to use when connecting to the database.
            database (str): The name of the database to connect to.

        Returns:
            None

        Examples:
            To create a new instance of the Database class:
            >>> from modules.database import Database
            >>> from modules.vault import Vault
            >>> vault = Vault()
            >>> db = Database(vault)
        """
        db_configuration = vault.read_secret(
            path='configurations/database'
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

    def _prepare_db(self):
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
                'chat_id VARCHAR(255) NOT NULL, '
                'scheduled_time datetime NOT NULL, '
                'timestamp datetime NOT NULL DEFAULT CURRENT_TIMESTAMP, '
                'state VARCHAR(255) NOT NULL DEFAULT \'waiting\''
            )
        )
        # Create a table for the message processed
        # After processing from the queue, the record should be moved to this table
        # and enriched with additional data
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
                'timestamp datetime NOT NULL DEFAULT CURRENT_TIMESTAMP, '
                'state VARCHAR(255) NOT NULL DEFAULT \'processed\''
            )
        )
        # Create a table for service migrations when updating the service
        # The table stores the name of the migration and its version
        self._create_table(
            table_name='migrations',
            columns=(
                'id SERIAL PRIMARY KEY, '
                'name VARCHAR(255) NOT NULL,'
                'version VARCHAR(255) NOT NULL, '
                'timestamp datetime NOT NULL DEFAULT CURRENT_TIMESTAMP'
            )
        )
        # Create a table for blocking exceptions (locks)
        # This table will record the locks caused by various exceptions when the bot is running.
        # These locks will block various bot functionality until manual intervention.
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
                'timestamp datetime NOT NULL DEFAULT CURRENT_TIMESTAMP'
            )
        )
        # Add kind of locks to the table
        # The table stores the name of the lock and its description
        self._insert(
            table_name='locks',
            columns='name, behavior, description, caused_by, tip',
            values=(
                '\'Unauthorized\', '
                '\'block:downloader_class\', '
                '\'Locks the post downloading functionality\', '
                '\'401:unauthorized\'',
                '\'Instagram session expired, invalid credentials or account is blocked\''
            )
        )
        self._insert(
            table_name='locks',
            columns='name, behavior, description, caused_by, tip',
            values=(
                '\'BadRequest\', '
                '\'block:downloader_class:post_link\', '
                '\'Locks the specified post downloading functionality\', '
                '\'400:badrequest\'',
                '\'When trying to upload content, an error occurs with an invalid request\''
            )
        )

    def _migrations(self):
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
        migrations_dir = os.path.join(os.path.dirname(__file__), 'migrations')

        for migration_file in os.listdir(migrations_dir):

            if migration_file.endswith('.py'):
                migration_module_name = migration_file[:-3]

                if not self._is_migration_executed(migration_module_name):
                    migration_module = importlib.import_module(migration_module_name)
                    migration_module.execute(self)
                    self._mark_migration_as_executed(migration_module_name)

    def _is_migration_executed(self, migration_name):
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
        query = f"SELECT id FROM migrations WHERE name = '{migration_name}'"
        self.cursor.execute(query)
        return self.cursor.fetchone() is not None

    def _mark_migration_as_executed(self, migration_name):
        """
        Inserts a migration into the migrations table to mark it as executed.

        Args:
            migration_name (str): The name of the migration to mark as executed.

        Returns:
            None

        Examples:
            >>> _mark_migration_as_executed('create_users_table')
        """
        query = f"INSERT INTO migrations (name, version) VALUES ('{migration_name}', '{migration_name}')"
        self.cursor.execute(query)
        self.database_connection.commit()

    def _create_table(self, table_name, columns):
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

    def _insert(self, table_name, columns, values):
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

    def _select(self, table_name: str, columns: str, condition: str) -> list:
        """
        Selects data from a table in the database based on the given condition.

        Args:
        table_name (str): The name of the table to select data from.
        columns (str): The columns to select data from.
        condition (str): The condition to filter the data by.

        Returns:
        list: A list of tuples containing the selected data.

        Examples:
        >>> db = Database()
        >>> db._select("users", "username, email", "age > 18")
        [('john_doe', 'john_doe@example.com'), ('jane_doe', 'jane_doe@example.com')]
        """
        self.cursor.execute(f"SELECT {columns} FROM {table_name} WHERE {condition}")
        return self.cursor.fetchall()

    def _update(self, table_name, set, condition):
        """
        Update the specified table with the given set of values based on the specified condition.

        Args:
            table_name (str): The name of the table to update.
            set (str): The set of values to update in the table.
            condition (str): The condition to use for updating the table.

        Returns:
            None

        Examples:
            To update the 'users' table with a new username and password for a user with ID 1:
            >>> _update('users', "username='new_username', password='new_password'", "id=1")
        """
        self.cursor.execute(f"UPDATE {table_name} SET {set} WHERE {condition}")
        self.database_connection.commit()

    def _delete(self, table_name: str, condition: str) -> None:
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

    def _close(self):
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
        message: dict = None
    ) -> str:
        """
        Add a message to the queue table in the database.

        Args:
            message (dict): A dictionary containing the message details.

        Parameters:
            user_id (str): The user ID of the message sender.
            post_id (str): The ID of the post the message is related to.
            post_url (str): The URL of the post the message is related to.
            post_owner (str): The username of the post owner.
            link_type (str): The type of link in the message.
            message_id (str): The ID of the message.
            chat_id (str): The ID of the chat the message belongs to.
            scheduled_time (str): The time the message is scheduled to be sent.

        Returns:
            str: A message indicating that the message was added to the queue.

        Examples:
            >>> message = {
            ...     'user_id': '12345',
            ...     'post_id': '67890',
            ...     'post_url': 'https://www.instagram.com/p/67890/',
            ...     'post_owner': 'johndoe',
            ...     'link_type': 'profile',
            ...     'message_id': 'abcde',
            ...     'chat_id': 'xyz',
            ...     'scheduled_time': '2022-01-01 12:00:00'
            ... }
            >>> add_message_to_queue(message)
            'abcde: added to queue'
        """
        self._insert(
            table_name='queue',
            columns='user_id, post_id, post_url, post_owner, link_type, message_id, chat_id, scheduled_time',
            values=(
                f"'{message.get('user_id', None)}', "
                f"'{message.get('post_id', None)}', "
                f"'{message.get('post_url', None)}', "
                f"'{message.get('post_owner', None)}', "
                f"'{message.get('link_type', None)}', "
                f"'{message.get('message_id', None)}', "
                f"'{message.get('chat_id', None)}', "
                f"'{message.get('scheduled_time', None)}'"
            )
        )

        return f"{message.get('message_id', None)}: added to queue"

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
            set (str): The new value for the state column.
            condition (str): The condition to use to select the row to update.

        Returns:
            str: A response message indicating the status of the update.

        Examples:
            >>> update_message_state_in_queue('123', 'processed', download_status='completed', upload_status='pending')
            '456: processed'
        """
        self._update(
            table_name='queue',
            set=f"state = '{state}'",
            condition=f"post_id = '{post_id}'"
        )

        if state == 'processed':
            processed_message = self._select(
                table_name='queue',
                columns='*',
                condition=f"post_id = '{post_id}'",
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
                    f"'{kwargs.get('download_status', None)}', "
                    f"'{kwargs.get('upload_status', None)}', "
                    f"'{processed_message[0][10]}'"
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

    def set_lock(
        self,
        lock_name: str = None
    ) -> str:
        """
        Set a lock in the database.

        Args:
            lock_name (str): The name of the lock to set.

        Returns:
            str: A message indicating that the lock has been set.

        Examples:
            >>> set_lock('example_lock')
            'example_lock: locked'
        """
        self._update(
            table_name='locks',
            set='enabled = TRUE',
            condition=f"name = '{lock_name}'"
        )

        return f"{lock_name}: locked"

    def reset_lock(
        self,
        lock_name: str = None
    ) -> str:
        """
        Resets the lock with the given name by setting its 'enabled' field to False.

        Args:
            lock_name (str): The name of the lock to reset.

        Returns:
            str: A message indicating that the lock has been unlocked.

        Examples:
            >>> reset_lock('my_lock')
            'my_lock: unlocked'
        """
        self._update(
            table_name='locks',
            set='enabled = FALSE',
            condition=f"name = '{lock_name}'"
        )

        return f"{lock_name}: unlocked"
