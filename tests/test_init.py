"""
A test for quick setup of the dev environment for testing the release.
"""
import subprocess
import pytest


@pytest.mark.order(1)
def test_init_dev_environment(vault_configuration_data, prepare_vault):
    """
    Check the function for the user who is allow access to the bot
    """
    _ = vault_configuration_data
    command = (
        "export VAULT_ADDR=http://vault-server:8200 && "
        f"export VAULT_APPROLE_ID={prepare_vault['id']} && "
        f"export VAULT_APPROLE_SECRETID={prepare_vault['secret-id']} && "
        "docker compose -f docker-compose.yml up -d --force-recreate --build pyinstabot-downloader"
    )
    with subprocess.Popen(command, shell=True):
        print("Running docker-compose.yml...")
