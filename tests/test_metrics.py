"""
This module contains tests for the database module.
"""
import requests
import pytest


@pytest.mark.order(13)
def test_metrics_instance(metrics_class, database_class):
    """
    Checking the creation of a metrics instance.
    """
    assert metrics_class.port == 8000
    assert metrics_class.interval == 5
    assert metrics_class.database == database_class
    assert metrics_class.thread_status_gauge is not None
    assert metrics_class.access_granted_counter is not None
    assert metrics_class.access_denied_counter is not None
    assert metrics_class.processed_messages_counter is not None
    assert metrics_class.queue_length_gauge is not None


@pytest.mark.order(14)
def test_metrics_users_stats(metrics_class, postgres_users_test_data):
    """
    Checking the collection of user statistics.
    """
    _ = postgres_users_test_data
    response = requests.get(f"http://0.0.0.0:{metrics_class.port}/", timeout=10)
    print(response.text)
    assert "pytest_access_granted_total" in response.text
    assert "pytest_access_denied_total" in response.text
    assert "pytest_access_granted_total 5.0" in response.text
    assert "pytest_access_denied_total 1.0" in response.text


@pytest.mark.order(15)
def test_metrics_threads_status(metrics_class):
    """
    Checking the collection of thread statistics.
    """
    response = requests.get(f"http://0.0.0.0:{metrics_class.port}/", timeout=10)
    assert "pytest_thread_status" in response.text
    assert 'pytest_thread_status{thread_name="MainThread"} 1.0' in response.text


@pytest.mark.order(16)
def test_metrics_messages(metrics_class, postgres_queue_test_data, postgres_processed_test_data):
    """
    Checking the collection of processed and queued messages statistics.
    """
    _ = postgres_queue_test_data
    _ = postgres_processed_test_data
    response = requests.get(f"http://0.0.0.0:{metrics_class.port}/", timeout=10)
    print(response.text)
    assert "pytest_processed_messages_total" in response.text
    assert "pytest_queue_length" in response.text
    assert "pytest_processed_messages_total 3.0" in response.text
    assert "pytest_queue_length 3.0" in response.text
