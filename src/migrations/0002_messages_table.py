# pylint: disable=C0103,R0914
"""
Add additional column 'created_at' and replace column 'timestamp' with 'updated_at' in the messages table.
https://github.com/obervinov/pyinstabot-downloader/issues/62
"""
VERSION = '1.0'
NAME = '0002_messages_table'


def execute(obj):
    """
    Add additional column 'created_at' and replace column 'timestamp' with 'updated_at' in the messages table.

    Args:
        obj: An obj containing the database connection and cursor, as well as the Vault instance.

    Returns:
        None
    """
    # database settings
    table_name = 'messages'
    rename_columns = [('timestamp', 'updated_at')]
    add_columns = [('created_at', 'TIMESTAMP', 'DEFAULT CURRENT_TIMESTAMP')]

    # check if the table exists and has the necessary schema for execute the migration
    # check table
    obj.cursor.execute("SELECT * FROM information_schema.tables WHERE table_schema = 'public' AND table_name = %s;", (table_name,))
    table = obj.cursor.fetchone()
    obj.cursor.close()
    # check columns in the table
    obj.cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = %s;", (table_name,))
    columns = [row[0] for row in obj.cursor.fetchall()]
    obj.cursor.close()

    if not table:
        print(f"{NAME}: The {table_name} table does not exist. Skip the migration.")
    elif len(columns) < 1:
        print(f"{NAME}: The {table_name} table does not have the necessary columns to execute the migration. Skip the migration.")
    else:
        print(f"{NAME}: Renaming columns in the {table_name} table...")
        for column in rename_columns:
            obj.cursor.execute(f"ALTER TABLE {table_name} RENAME COLUMN {column[0]} TO {column[1]}")
            obj.database_connection.commit()
        print(f"{NAME}: Columns in the {table_name} table have been renamed")
        for column in add_columns:
            obj.cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column[0]} {column[1]} DEFAULT {column[2]}")
            obj.database_connection.commit()
