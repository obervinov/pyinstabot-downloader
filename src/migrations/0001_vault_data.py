# pylint: disable=C0103,R0914
"""
Migrates historical data from the Vault to the processed table in the database.
https://github.com/obervinov/pyinstabot-downloader/issues/30
"""
VERSION = '1.0'
NAME = '0001_vault_data'


def execute(obj):
    """
    Migrates historical data from the Vault to the processed table in the database.

    Args:
        obj: An obj containing the database connection and cursor, as well as the Vault instance.

    Returns:
        None
    """
    # database settings
    table_name = 'processed'
    columns = 'user_id, post_id, post_url, post_owner, link_type, message_id, chat_id, download_status, upload_status, state'

    # information about owners
    owners = obj.vault.list_secrets(path='history/')
    owners_counter = len(owners)
    print(f"Founded {owners_counter} owners in history")

    # reade history form Vault
    for owner in owners:
        # information about owner posts
        posts = obj.vault.read_secret(path=f"history/{owner}")
        posts_counter = len(posts)
        print(f"{NAME}: Founded {posts_counter} posts in history/{owner}")

        for post in posts:
            user_id = next(iter(obj.vault.read_secret(path='configuration/users').keys()))
            post_id = post
            post_url = f"https://www.instagram.com/p/{post}"
            post_owner = owner
            link_type = 'post'
            message_id = 'unknown'
            chat_id = next(iter(obj.vault.read_secret(path='configuration/users').keys()))
            download_status = 'completed'
            upload_status = 'completed'
            state = 'processed'

            values = (
                f"'{user_id}', "
                f"'{post_id}', "
                f"'{post_url}', "
                f"'{post_owner}', "
                f"'{link_type}', "
                f"'{message_id}', "
                f"'{chat_id}', "
                f"'{download_status}', "
                f"'{upload_status}', "
                f"'{state}'"
            )

            print(f"{NAME}: Migrating {post_id} from history/{owner}")
            obj.cursor.execute(f"INSERT INTO {table_name} ({columns}) VALUES ({values})")
            obj.database_connection.commit()
            print(f"{NAME}: Post {post_id} from history/{owner} has been added to processed table")
