"""
This test is necessary to check how the bot's logic for receiving and processing messages works.
"""
import pytest
from src import bot


@pytest.mark.order(0)
def test_post_link_flow(vault_client):
    """
    A test to check the flow of loading a specific post by link
    """
    bot.get_post_account(
        message=
    )


    assert response['request_id']
