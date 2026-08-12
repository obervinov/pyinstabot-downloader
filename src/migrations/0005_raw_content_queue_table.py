# pylint: disable=C0103,R0801
"""
Create raw_content_queue table for batch scan/process flow in WebUI raw content ingestion.
"""

VERSION = '1.0'
NAME = '0005_raw_content_queue_table'


def execute(obj):
    """
    Create raw_content_queue table and indexes.

    Args:
        obj: Database client instance.
    """
    table_name = 'raw_content_queue'
    print(f"{NAME}: Start migration for table {table_name}...")

    conn = obj.get_connection()
    with conn.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS raw_content_queue (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                item_name VARCHAR(1024) NOT NULL,
                item_path VARCHAR(2048) NOT NULL,
                mode VARCHAR(50) NOT NULL DEFAULT 'single',
                post_id VARCHAR(255),
                post_url VARCHAR(2048),
                post_owner VARCHAR(255),
                source VARCHAR(100),
                status VARCHAR(50) NOT NULL DEFAULT 'scanned',
                scan_id VARCHAR(255),
                destination VARCHAR(2048),
                files_moved INTEGER,
                error_message TEXT,
                content_files TEXT DEFAULT '[]',
                scanned_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                finished_at TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, item_path)
            )
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_raw_content_queue_user_status
            ON raw_content_queue (user_id, status)
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_raw_content_queue_scan_id
            ON raw_content_queue (scan_id)
            """
        )

    conn.commit()
    obj.close_connection(conn)
    print(f"{NAME}: Migration completed")
