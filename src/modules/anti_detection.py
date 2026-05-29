"""
Anti-detection module for Instagram bot behavior randomization.

This module provides utilities to make bot behavior appear more human-like:
- Random delays between requests
- Noise requests (feed browsing, profile views, likes)
- Request pattern randomization
"""
import random
import time
from typing import Optional
from logger import log


class AntiDetection:
    """
    Utilities for anti-detection behavior.
    """

    def __init__(
        self,
        min_delay: float = 0.5,
        max_delay: float = 3.0,
        noise_probability: float = 0.15,
        like_probability: float = 0.05,
    ):
        """
        Initialize anti-detection settings.

        Args:
            min_delay: Minimum delay between requests in seconds
            max_delay: Maximum delay between requests in seconds
            noise_probability: Probability to add noise request (0.0-1.0)
            like_probability: Probability to like a random post (0.0-1.0)
        """
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.noise_probability = noise_probability
        self.like_probability = like_probability

    def random_delay(self, operation: str = "request") -> None:
        """
        Add random delay to simulate human behavior.

        Args:
            operation: Description of operation for logging
        """
        delay = random.uniform(self.min_delay, self.max_delay)
        log.debug(f"[AntiDetection] Random delay {delay:.2f}s before {operation}")
        time.sleep(delay)

    def should_add_noise(self) -> bool:
        """
        Determine if noise request should be added.

        Returns:
            True if noise should be added based on probability
        """
        return random.random() < self.noise_probability

    def should_like_post(self) -> bool:
        """
        Determine if random post should be liked.

        Returns:
            True if should like based on probability
        """
        return random.random() < self.like_probability

    def add_feed_noise(self, client, username: str) -> None:
        """
        Add noise by viewing random feed posts.

        Args:
            client: Instagram client instance
            username: Username for context logging
        """
        try:
            log.debug(f"[AntiDetection] Adding feed noise for {username}")
            # Get timeline feed (simulates user browsing)
            feed = client.get_timeline_feed()
            if feed and len(feed) > 0:
                # View 1-3 random posts from feed
                view_count = random.randint(1, min(3, len(feed)))
                random_posts = random.sample(feed, view_count)

                for post in random_posts:
                    # Just accessing media_info simulates viewing
                    _ = client.media_info(post.pk)
                    self.random_delay("feed post view")

                log.debug(f"[AntiDetection] Viewed {view_count} feed posts as noise")
        except Exception as e:
            log.warning(f"[AntiDetection] Failed to add feed noise: {e}")

    def add_like_noise(self, client, username: str) -> None:
        """
        Add noise by liking a random post from feed.

        Args:
            client: Instagram client instance
            username: Username for context logging
        """
        try:
            log.debug(f"[AntiDetection] Adding like noise for {username}")
            # Get timeline feed
            feed = client.get_timeline_feed()
            if feed and len(feed) > 0:
                # Like one random post
                random_post = random.choice(feed)
                client.media_like(random_post.pk)
                log.debug(f"[AntiDetection] Liked random post {random_post.pk} as noise")
                self.random_delay("like noise")
        except Exception as e:
            log.warning(f"[AntiDetection] Failed to add like noise: {e}")

    def add_profile_noise(self, client, target_username: str) -> None:
        """
        Add noise by viewing target user profile before downloading.

        Args:
            client: Instagram client instance
            target_username: Target username to view
        """
        try:
            log.debug(f"[AntiDetection] Viewing profile {target_username} as noise")
            # View user profile info (simulates checking profile before downloading)
            user_info = client.user_info_by_username(target_username)
            self.random_delay("profile view")

            # Sometimes view user's feed too (realistic behavior)
            if random.random() < 0.3:  # 30% chance
                user_medias = client.user_medias(user_info.pk, amount=5)
                log.debug(f"[AntiDetection] Viewed {len(user_medias)} recent posts from {target_username}")
                self.random_delay("profile media browsing")
        except Exception as e:
            log.warning(f"[AntiDetection] Failed to add profile noise: {e}")

    def wrap_download_with_behavior(
        self,
        client,
        download_func,
        username: str,
        target_username: Optional[str] = None,
    ):
        """
        Wrap download operation with human-like behavior.

        Args:
            client: Instagram client instance
            download_func: Function to execute for download
            username: Bot username for logging
            target_username: Target username being downloaded (if applicable)

        Returns:
            Result of download_func
        """
        # Pre-download behavior
        if target_username and self.should_add_noise():
            self.add_profile_noise(client, target_username)

        # Random delay before main operation
        self.random_delay("download operation")

        # Execute main download
        result = download_func()

        # Post-download behavior
        if self.should_add_noise():
            self.add_feed_noise(client, username)

        if self.should_like_post():
            self.add_like_noise(client, username)

        # Random delay after operation
        self.random_delay("post-download")

        return result
