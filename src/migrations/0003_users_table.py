# pylint: disable=C0103,R0914,R0801
"""
Add additional column 'status' in the users table.
https://github.com/obervinov/users-package/blob/v3.0.0/tests/postgres/tables.sql
"""
VERSION = '1.0'
NAME = '0003_users_table'


def execute(obj):
    """
    Add additional column 'status' in the users table.

    Args:
        obj: An obj containing the database connection and cursor, as well as the Vault instance.

    Returns:
        None
    """
    # database settings
    table_name = 'users'
    add_columns = [('status', 'VARCHAR(255)', "'denied'")]
    update_columns = [('user_id', 'VARCHAR(255)', 'UNIQUE NOT NULL')]
    print(f"{NAME}: Start migration for the {table_name} table: Add columns {add_columns} and update columns {update_columns}...")

    # check if the table exists and has the necessary schema for execute the migration
    conn = obj.get_connection()
    with conn.cursor() as cursor:
        # check table
        cursor.execute("SELECT * FROM information_schema.tables WHERE table_schema = 'public' AND table_name = %s;", (table_name,))
        table = cursor.fetchone()

        # check columns in the table
        cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = %s;", (table_name,))
        columns = [row[0] for row in cursor.fetchall()]

        if not table:
            print(f"{NAME}: The {table_name} table does not exist. Skip the migration.")

        elif len(columns) < 1:
            print(f"{NAME}: The {table_name} table does not have the necessary columns to execute the migration. Skip the migration.")

        else:
            for column in add_columns:
                if column[0] in columns:
                    print(f"{NAME}: The {table_name} table already has the {column[0]} column. Skip adding.")
                else:
                    try:
                        print(f"{NAME}: Add column {column[0]} to the {table_name} table...")
                        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column[0]} {column[1]} DEFAULT {column[2]}")
                        conn.commit()
                        print(f"{NAME}: Column {column[0]} has been added to the {table_name} table.")
                    except obj.errors.DuplicateColumn as error:
                        print(f"{NAME}: Columns in the {table_name} table have already been added. Skip adding: {error}")
                        conn.rollback()
                    except obj.errors.FeatureNotSupported as error:
                        print(f"{NAME}: Columns in the {table_name} table have not been added. Skip adding: {error}")
                        conn.rollback()
