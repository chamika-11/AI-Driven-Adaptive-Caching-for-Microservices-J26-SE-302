"""
volatility.py — EWMA-based Cache-Key Volatility Engine.

Volatility measures how frequently the underlying data for a cache key changes
in the database. High volatility means the cached value goes stale quickly, so
the TTL Fusion Engine will apply a heavy penalty to reduce the TTL.

Formula:
    Vol(t) = α * updates_per_minute + (1 - α) * Vol(t-1)

where α (alpha) controls how quickly the engine reacts to recent changes.
A higher α gives more weight to recent observations (fast reaction).
"""

import logging
from datetime import datetime

import pandas as pd

# HotKeyDetector is a standalone module — re-exported here for convenience
# so callers that previously imported both from volatility still work.
from hotkey_detector import HotKeyDetector  # noqa: F401

logger = logging.getLogger(__name__)


class VolatilityEngine:
    """
    Exponentially-Weighted Moving Average (EWMA) volatility tracker.

    Args:
        alpha (float): Smoothing factor in [0, 1]. Higher = more reactive.
                       Default: 0.3.
    """

    def __init__(self, alpha: float = 0.3):
        if not 0.0 < alpha <= 1.0:
            raise ValueError(f"alpha must be in (0, 1], got {alpha}")
        self.alpha = alpha
        self._volatilities: dict[str, float] = {}
        logger.info("VolatilityEngine initialised with alpha=%.2f", alpha)

    def update(self, key: str, current_time: datetime, db_update_df: pd.DataFrame) -> float:
        """
        Compute and update the EWMA volatility score for `key`.

        Args:
            key: Cache key to evaluate.
            current_time: The reference "now" timestamp (timezone-naive).
            db_update_df: DataFrame with columns ['timestamp', 'cache_key'].
                          Must already be loaded by the caller — do NOT read
                          CSV inside this method (performance).

        Returns:
            Volatility score in [0.0, 1.0].
        """
        # Check if live CDC mutations already set a higher volatility for this key
        live_vol = self._volatilities.get(key, 0.0)

        # Calculate base mutation rate from DB update records
        if not db_update_df.empty and "cache_key" in db_update_df.columns:
            key_updates = db_update_df[db_update_df["cache_key"] == key]
            write_count = len(key_updates)
            # Normalise: 100 writes/hr = 1.0 (e.g., 34 writes in trace = 0.340)
            base_rate = round(min(1.0, write_count / 100.0), 3)
        else:
            base_rate = 0.0

        current_rate = max(base_rate, live_vol)

        # EWMA update: Vol(t) = α * current_rate + (1 - α) * Vol(t-1)
        if key not in self._volatilities:
            self._volatilities[key] = current_rate
        else:
            prev = self._volatilities[key]
            # Smoothly update while preserving live CDC spikes
            self._volatilities[key] = max(
                live_vol,
                self.alpha * current_rate + (1.0 - self.alpha) * prev
            )

        score = max(0.0, min(1.0, round(self._volatilities[key], 3)))
        return score

    def record_mutation(self, key: str, weight: float = 0.5) -> float:
        """
        Directly record an incoming real-time CDC mutation from Debezium/Kafka.
        
        Bumps the EWMA volatility score for `key` so that incoming mutations immediately
        impact the TTL without waiting for batch CSV updates.
        """
        prev = self._volatilities.get(key, 0.0)
        # Apply EWMA bump
        new_vol = min(1.0, max(0.0, self.alpha * weight + (1.0 - self.alpha) * max(prev, 0.2)))
        self._volatilities[key] = new_vol
        logger.info("Real-time CDC mutation recorded for key='%s': prev=%.3f -> new=%.3f", key, prev, new_vol)
        return new_vol

    def get(self, key: str) -> float:
        """Return the last known volatility for a key, or 0.0 if unseen."""
        return self._volatilities.get(key, 0.0)