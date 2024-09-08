"""
This module contains tests for the database module.
"""
import requests
import pytest


@pytest.mark.order(13)
def test_metrics_instance(metrics_class, database_class, vault_instance):
    """
    Checking the creation of a metrics instance.
    """
    assert metrics_class.port == 8000
    assert metrics_class.interval == 1
    assert metrics_class.vault == vault_instance
    assert metrics_class.database == database_class
    assert metrics_class.thread_status_gauge is not None
    assert metrics_class.access_granted_counter is not None
    assert metrics_class.access_denied_counter is not None
    assert metrics_class.processed_messages_counter is not None
    assert metrics_class.queue_length_gauge is not None


@pytest.mark.order(14)
def test_metrics_users_stats(metrics_class):
    """
    Checking the collection of user statistics.
    """
    response = requests.get(f"http://0.0.0.0:{metrics_class.port}/", timeout=10)
    assert "pytest_thread_status" in response.text
