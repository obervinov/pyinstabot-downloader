# pylint: disable=C0103,R0801
"""
Create app_config table for universal application configuration storage (component-agnostic).
Stores configuration for any component/module (raw_processing, downloader, uploader, etc.) as JSON.
Supports per-user, per-component, or global configurations via JSON keys.
"""

VERSION = '1.0'
NAME = '0006_app_config_table'


def execute(obj):
    """
    Create app_config table for generic application configuration storage.
    Supports per-user configurations identified by user_id in the config scope.

    Args:
        obj: Database client instance.
    """
    table_name = 'app_config'
    print(f"{NAME}: Start migration for table {table_name}...")

    conn = obj.get_connection()
    with conn.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS app_config (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(255),
                component VARCHAR(100) NOT NULL,
                config JSONB NOT NULL DEFAULT '{}',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, component)
            )
            """
        )
        print(f"{NAME}: Created {table_name} table")

        cursor.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table_name}_user_id ON {table_name}(user_id)"
        )
        print(f"{NAME}: Created index on user_id")

        cursor.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table_name}_component ON {table_name}(component)"
        )
        print(f"{NAME}: Created index on component")

    conn.commit()
    obj.close_connection(conn)
    print(f"{NAME}: Migration completed successfully")
