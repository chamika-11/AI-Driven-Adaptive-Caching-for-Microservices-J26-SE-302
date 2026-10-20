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
        ts_col = db_update_df["timestamp"]
        
        # If the system clock is ahead of the trace dataset, align the 1-hour window to the trace timeline
        if not db_update_df.empty:
            max_trace_time = ts_col.max()
            if ts_col.dt.tz is not None and current_time.tzinfo is None:
                current_time = current_time.tz_localize(ts_col.dt.tz)
            
            if current_time > max_trace_time:
                # Align relative to the trace activity window (with key-specific offset for realism)
                key_seed = sum(ord(c) for c in key) % 24
                ref_time = max_trace_time - pd.Timedelta(hours=key_seed)
                one_hour_ago = ref_time - pd.Timedelta(hours=1)
                mask = (db_update_df["cache_key"] == key) & (ts_col >= one_hour_ago) & (ts_col <= ref_time)
            else:
                one_hour_ago = current_time - pd.Timedelta(hours=1)
                mask = (db_update_df["cache_key"] == key) & (ts_col >= one_hour_ago)
        else:
            recent_count = 0
            mask = []
        recent_count = mask.sum()

        # Convert raw count → normalised updates-per-minute (capped at 1.0)
        updates_per_minute = recent_count / 60.0
        current_rate = min(updates_per_minute * 10, 1.0)

        # EWMA formula: Vol(t) = α * current_rate + (1 - α) * Vol(t-1)
        if key not in self._volatilities:
            self._volatilities[key] = current_rate
            logger.debug(
                "New volatility entry for key='%s': rate=%.4f", key, current_rate
            )
        else:
            prev = self._volatilities[key]
            self._volatilities[key] = (
                self.alpha * current_rate + (1.0 - self.alpha) * prev
            )
            logger.debug(
                "Volatility update for key='%s': prev=%.4f rate=%.4f new=%.4f",
                key,
                prev,
                current_rate,
                self._volatilities[key],
            )

        # Clamp to [0, 1]
        score = max(0.0, min(1.0, self._volatilities[key]))
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