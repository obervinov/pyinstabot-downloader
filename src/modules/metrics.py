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
        vault: object = None,
        database: object = None
    ) -> None:
        self.port = port
        self.interval = interval
        self.vault = vault
        self.database = database
        self.thread_status_gauge = Gauge('thread_status', 'Thread status (1 = running, 0 = not running)', ['thread_name'])
        if vault:
            self.access_granted_counter = Gauge('access_granted_total', 'Total number of users granted access')
            self.access_denied_counter = Gauge('access_denied_total', 'Total number of users denied access')
        if database:
            self.processed_messages_counter = Gauge('processed_messages_total', 'Total number of processed messages')
            self.queue_length_gauge = Gauge('queue_length', 'Queue length')

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
        processed_messages_total = 0
        queue_length_total = 0
        for user in self.database.get_users():
            processed_messages = self.database.get_user_processed(user_id=user[0])
            queue_length = self.database.get_user_queue(user_id=user[0])
            processed_messages_total += len(processed_messages[user[0]])
            queue_length_total += len(queue_length[user[0]])
        self.processed_messages_counter.set(processed_messages_total)
        self.queue_length_gauge.set(queue_length_total)

    def run(self, threads: list) -> None:
        """
        The method starts the server and collects metrics.
        """
        start_http_server(self.port)
        log.info('[Metrics]: Metrics server started on port %s', self.port)
        while True:
            self.collect_users_stats()
            time.sleep(self.interval)
            for thread in threads:
                self.update_thread_status(thread.name, thread.is_alive())
