# pylint: disable=C0103,R0914,R0801
"""
Migration for the vault users data to the users table in the database.
https://github.com/obervinov/users-package/blob/v3.0.0/tests/postgres/tables.sql
"""
VERSION = '1.0'
NAME = '0004_vault_users_data'


def execute(obj):
    """
    Migration for the vault users data to the users table in the database.

    Args:
        obj: An obj containing the database connection and cursor, as well as the Vault instance.

    Returns:
        None
    """
    # database settings
    table_name = 'users'
    print(f"{NAME}: Start migration from the vault to the {table_name} table...")

    # check if the table exists for execute the migration
    conn = obj.get_connection()
    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM information_schema.tables WHERE table_schema = 'public' AND table_name = %s;", (table_name,))
        table = cursor.fetchone()

        if not table:
            print(f"{NAME}: The {table_name} table does not exist. Skip the migration.")

        else:
            try:
                users = obj.vault.kv2engine.list_secrets(path='data/users')
                users_counter = len(users)
                print(f"{NAME}: Founded {users_counter} users in users data")

                for user in users:
                    user_last_state = obj.json.loads(obj.vault.kv2engine.read_secret(path=f"data/users/{user}"))

                    user_id = user
                    chat_id = 'unknown'
                    status = user_last_state.get('status', 'unknown')

                    values = f"'{user_id}', '{chat_id}', '{status}'"

                    print(f"{NAME}: Migrating user {user_id} to the {table_name} table...")
                    with conn.cursor() as cursor:
                        cursor.execute(f"INSERT INTO {table_name} (user_id, chat_id, status) VALUES ({values})")
                        conn.commit()
                        print(f"{NAME}: User {user_id} has been added to the {table_name} table")
                print(f"{NAME}: Migration has been completed")
            # pylint: disable=broad-exception-caught
            except Exception as migration_error:
                print(
                    f"{NAME}: Migration cannot be completed due to an error: {migration_error}. "
                    "Perhaps the history is empty or the Vault secrets path does not exist and migration isn't unnecessary."
                    "It's not a critical error, so the migration will be skipped."
                )
        obj.close_connection(conn)
