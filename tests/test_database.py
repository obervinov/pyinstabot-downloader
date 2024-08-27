"""
This module contains tests for the database module.
"""

import os
import sys
import json
import importlib
import pytest
import psycopg2
from psycopg2 import pool
from src.modules.database import DatabaseClient


# pylint: disable=too-many-locals
@pytest.mark.order(2)
def test_init_database_client(prepare_vault, vault_instance, vault_configuration_data, postgres_instance):
    """
    Checking an initialized database client
    """
    _ = vault_configuration_data
    _, cursor = postgres_instance
    db_role = prepare_vault['db_role']
    database = DatabaseClient(vault=vault_instance, db_role=db_role)

    # Check general attributes
    assert isinstance(database.vault, object)
    assert isinstance(database.db_role, str)
    assert isinstance(database.database_connections, pool.SimpleConnectionPool)

    # Check tables creation in the database
    cursor.execute("SELECT * FROM information_schema.tables WHERE table_schema = 'public'")
    tables_list = cursor.fetchall()
    tables_configuration_path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '../src/configs/databases.json'))
    with open(tables_configuration_path, encoding='UTF-8') as config_file:
        database_init_configuration = json.load(config_file)
    for table in database_init_configuration.get('Tables', None):
        if table['name'] not in [table[2] for table in tables_list]:
            assert False

    # Check migrations execution in the database
    cursor.execute("SELECT * FROM migrations")
    migrations_list = cursor.fetchall()
    assert len(migrations_list) > 0

    migrations_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../src/migrations'))
    sys.path.append(migrations_dir)
    migration_files = [f for f in os.listdir(migrations_dir) if f.endswith('.py')]
    migration_files.sort()
    for migration_file in migration_files:
        if not migration_file.endswith('.py'):
            assert False
        else:
            migration_module_name = migration_file[:-3]
            migration_module = importlib.import_module(name=migration_module_name)
            version = getattr(migration_module, 'VERSION', migration_module_name)
            name = getattr(migration_module, 'NAME', migration_module_name)
            if (version, name) not in migrations_list:
                print(f"Not found migration {version}:{name} in {migrations_list}") 


# @pytest.mark.order(4)
# def test_database_connection(prepare_vault, vault_instance, vault_configuration_data, postgres_instance):
#     """

#     """
#     _ = vault_configuration_data
#     _ = postgres_instance
#     db_role = prepare_vault['db_role']
#     database = DatabaseClient(vault=vault_instance, db_role=db_role)

#     connection = database.get_connection()
#     assert isinstance(connection, psycopg2.extensions.connection)
