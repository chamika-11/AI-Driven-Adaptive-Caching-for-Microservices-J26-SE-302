"""
hotkey_detector.py — Sliding-Window Hot-Key Detection.

A "hot key" is a cache key that receives an abnormally high number of requests
within a short time window (a traffic storm / stampede). When detected, the
TTL Fusion Engine overrides the calculated TTL with the maximum TTL to serve
as many requests as possible from cache.

Algorithm:
    - Maintain a deque of request timestamps per cache key.
    - On each request, evict timestamps older than `window_seconds`.
    - If the remaining count >= threshold, declare the key as HOT.

Time complexity: O(evicted) per call — amortised O(1) in steady state.
Space complexity: O(threshold) per key — bounded by maxlen on the deque.
"""

import time
import logging
from collections import deque

logger = logging.getLogger(__name__)


class HotKeyDetector:
    """
    Sliding-window counter for detecting hot/stampede cache keys.

    Args:
        threshold (int): Number of requests within `window_seconds` that
                         triggers a hot-key classification. Default: 1000.
        window_seconds (int): Length of the sliding window. Default: 60.
    """

    def __init__(self, threshold: int = 1000, window_seconds: int = 60):
        self.threshold = threshold
        self.window_seconds = window_seconds
        # key -> deque of monotonic timestamps (seconds)
        self._requests: dict[str, deque] = {}
        logger.info(
            "HotKeyDetector initialised — threshold=%d req / %ds window",
            threshold,
            window_seconds,
        )

    def record_request(self, key: str) -> bool:
        """
        Record one request for `key` and return whether the key is HOT.

        Args:
            key: The cache key being accessed.

        Returns:
            True if the key has exceeded the threshold in the sliding window.
        """
        now = time.monotonic()
        cutoff = now - self.window_seconds

        if key not in self._requests:
            # maxlen caps memory usage: once threshold+1 entries exist,
            # oldest are auto-evicted from the left.
            self._requests[key] = deque(maxlen=self.threshold + 100)

        bucket = self._requests[key]

        # Evict timestamps that have fallen outside the window
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

        # Record this request
        bucket.append(now)

        count = len(bucket)
        is_hot = count >= self.threshold

        if is_hot:
            logger.warning(
                "HOT KEY detected: key='%s' count=%d >= threshold=%d",
                key,
                count,
                self.threshold,
            )

        return is_hot

    def is_hot(self, key: str) -> bool:
        """
        Check whether a key is currently hot WITHOUT recording a new request.

        Useful for read-only inspection (e.g., health checks).
        """
        if key not in self._requests:
            return False
        now = time.monotonic()
        cutoff = now - self.window_seconds
        bucket = self._requests[key]
        # Count how many timestamps are still within the window
        count = sum(1 for ts in bucket if ts >= cutoff)
        return count >= self.threshold

    def reset(self, key: str) -> None:
        """Clear all recorded requests for a key (useful in tests)."""
        self._requests.pop(key, None)
        logger.debug("Reset request history for key='%s'", key)

    def stats(self, key: str) -> dict:
        """Return diagnostic stats for a key."""
        if key not in self._requests:
            return {"key": key, "count_in_window": 0, "is_hot": False}
        now = time.monotonic()
        cutoff = now - self.window_seconds
        count = sum(1 for ts in self._requests[key] if ts >= cutoff)
        return {
            "key": key,
            "count_in_window": count,
            "threshold": self.threshold,
            "window_seconds": self.window_seconds,
            "is_hot": count >= self.threshold,
        }
