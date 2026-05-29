"""
Request pacing helpers for downloader operations.

This module provides utilities for:
- randomized delays between API operations
- optional lightweight session warm-up requests
- spacing around download steps
"""
import random
import time
from typing import Optional
from logger import log


class AntiDetection:
    """
    Utilities for randomized request pacing and optional session warm-up.
    """

    def __init__(
        self,
        min_delay: float = 0.5,
        max_delay: float = 3.0,
        noise_probability: float = 0.15,
        like_probability: float = 0.05,
    ):
        """
        Initialize request pacing settings.

        Args:
            min_delay: Minimum delay between requests in seconds
            max_delay: Maximum delay between requests in seconds
            noise_probability: Probability to add optional warm-up requests (0.0-1.0)
            like_probability: Probability to add optional engagement actions (0.0-1.0)
        """
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.noise_probability = noise_probability
        self.like_probability = like_probability

    def random_delay(self, operation: str = "request") -> None:
        """
        Add randomized delay before an operation.

        Args:
            operation: Description of operation for logging
        """
        delay = random.uniform(self.min_delay, self.max_delay)
        log.debug(f"[AntiDetection] Random delay {delay:.2f}s before {operation}")
        time.sleep(delay)

    def should_add_noise(self) -> bool:
        """
        Determine if an optional warm-up request should be added.

        Returns:
            True if a warm-up request should be added based on probability
        """
        return random.random() < self.noise_probability

    def should_like_post(self) -> bool:
        """
        Determine if an optional engagement action should be added.

        Returns:
            True if the action should be added based on probability
        """
        return random.random() < self.like_probability

    def add_feed_noise(self, client, username: str) -> None:
        """
        Perform lightweight background feed reads.

        Args:
            client: Instagram client instance
            username: Username for context logging
        """
        try:
            log.debug(f"[AntiDetection] Running feed warm-up for {username}")
            feed = client.get_timeline_feed()
            if feed and len(feed) > 0:
                view_count = random.randint(1, min(3, len(feed)))
                random_posts = random.sample(feed, view_count)

                for post in random_posts:
                    _ = client.media_info(post.pk)
                    self.random_delay("feed post view")

                log.debug(f"[AntiDetection] Read {view_count} feed posts during warm-up")
        except Exception as e:
            log.warning(f"[AntiDetection] Feed warm-up failed: {e}")

    def add_like_noise(self, client, username: str) -> None:
        """
        Perform an optional engagement action on a feed item.

        Args:
            client: Instagram client instance
            username: Username for context logging
        """
        try:
            log.debug(f"[AntiDetection] Running optional engagement action for {username}")
            feed = client.get_timeline_feed()
            if feed and len(feed) > 0:
                random_post = random.choice(feed)
                client.media_like(random_post.pk)
                log.debug(f"[AntiDetection] Completed engagement action for post {random_post.pk}")
                self.random_delay("engagement action")
        except Exception as e:
            log.warning(f"[AntiDetection] Optional engagement action failed: {e}")

    def add_profile_noise(self, client, target_username: str) -> None:
        """
        Read target profile context before downloading.

        Args:
            client: Instagram client instance
            target_username: Target username to inspect
        """
        try:
            log.debug(f"[AntiDetection] Reading profile context for {target_username}")
            user_info = client.user_info_by_username(target_username)
            self.random_delay("profile view")

            if random.random() < 0.3:
                user_medias = client.user_medias(user_info.pk, amount=5)
                log.debug(f"[AntiDetection] Read {len(user_medias)} recent posts from {target_username}")
                self.random_delay("profile media browsing")
        except Exception as e:
            log.warning(f"[AntiDetection] Profile context read failed: {e}")

    def wrap_download_with_behavior(
        self,
        client,
        download_func,
        username: str,
        target_username: Optional[str] = None,
    ):
        """
        Wrap download operation with randomized pacing.

        Args:
            client: Instagram client instance
            download_func: Function to execute for download
            username: Bot username for logging
            target_username: Target username being downloaded (if applicable)

        Returns:
            Result of download_func
        """
        # Optional pre-download warm-up
        if target_username and self.should_add_noise():
            self.add_profile_noise(client, target_username)

        # Random delay before main operation
        self.random_delay("download operation")

        # Execute main download
        result = download_func()

        # Optional post-download warm-up
        if self.should_add_noise():
            self.add_feed_noise(client, username)

        if self.should_like_post():
            self.add_like_noise(client, username)

        # Random delay after operation
        self.random_delay("post-download")

        return result
