"""This module provides a way to expose metrics to Prometheus for monitoring the application."""
import time
import json

from prometheus_client import start_http_server, Gauge
from logger import log


# pylint: disable=too-many-instance-attributes
class Metrics():
    """
    This class provides a way to expose metrics to Prometheus for monitoring the application.
    """
    def __init__(
        self,
        port: int = None,
        interval: int = None,
        metrics_prefix: str = None,
        **kwargs
    ) -> None:
        """
        The method initializes the class instance with the necessary parameters.

        Args:
            :param port (int): port for the metrics server.
            :param interval (int): interval for collecting metrics.
            :param metrics_prefix (str): prefix for the metrics.

        Keyword Args:
            :param vault (Vault): instance of the Vault class.
            :param database (Database): instance of the Database class.

        Returns:
            None
        """
        self.port = port
        self.interval = interval
        self.vault = kwargs.get('vault', None)
        self.database = kwargs.get('database', None)
        self.thread_status_gauge = Gauge(f'{metrics_prefix}-thread_status', 'Thread status (1 = running, 0 = not running)', ['thread_name'])
        if self.vault:
            self.access_granted_counter = Gauge(f'{metrics_prefix}-access_granted_total', 'Total number of users granted access')
            self.access_denied_counter = Gauge(f'{metrics_prefix}-access_denied_total', 'Total number of users denied access')
        if self.database:
            self.processed_messages_counter = Gauge(f'{metrics_prefix}-processed_messages_total', 'Total number of processed messages')
            self.queue_length_gauge = Gauge(f'{metrics_prefix}-queue_length', 'Queue length')

    def collect_users_stats(self) -> None:
        """
        The method collects information about users access status and updates the gauge.
        """
        users = self.vault.list_secrets(path='data/users')
        access_granted_count = 0
        access_denied_count = 0

        for user in users:
            user_status = json.loads(self.vault.read_secret(path=f'data/users/{user}')['authentication'])
            if user_status.get('status') == 'denied':
                access_denied_count += 1
            elif user_status.get('status') == 'allowed':
                access_granted_count += 1

        self.access_granted_counter.set(access_granted_count)
        self.access_denied_counter.set(access_denied_count)

    def update_thread_status(self, thread_name, is_running) -> None:
        """
        The method updates the gauge with the status of the thread.
        """
        self.thread_status_gauge.labels(thread_name).set(1 if is_running else 0)

    def collect_messages_stats(self) -> None:
        """
        The method updates the gauge with the number of processed and queued messages.
        """
        processed_messages_count = 0
        queue_messages_count = 0
        for user in self.database.get_users():
            user_id = user[0]
            processed_messages = self.database.get_user_processed(user_id=user_id)
            queue_messages = self.database.get_user_queue(user_id=user_id)
            processed_messages_count += len(processed_messages.get(user_id, []))
            queue_messages_count = len(queue_messages.get(user_id, []))
        self.processed_messages_counter.set(processed_messages_count)
        self.queue_length_gauge.set(queue_messages_count)

    def run(self, threads: list) -> None:
        """
        The method starts the server and collects metrics.
        """
        start_http_server(self.port)
        log.info('[Metrics]: Metrics server started on port %s', self.port)
        while True:
            if self.vault:
                self.collect_users_stats()
            if self.database:
                self.collect_messages_stats()
            time.sleep(self.interval)
            for thread in threads:
                self.update_thread_status(thread.name, thread.is_alive())
