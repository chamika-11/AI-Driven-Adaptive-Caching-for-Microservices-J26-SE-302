"""
synthetic_data.py — Synthetic Training Data Generator.

Generates two CSV files:
  - raw_logs.csv     : Simulated cache access logs with daily/weekly patterns.
  - db_updates.csv   : Simulated database write events for volatility scoring.

Patterns modelled:
  - Daily peaks at 09:00 and 14:00 (Gaussian envelopes).
  - Higher traffic on weekdays (Mon–Fri) vs weekends.
  - Per-key base popularity drawn from a uniform random distribution.
  - DB update frequency per key drawn from a discrete set of rates.
"""

import logging
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("synthetic_data")


def generate_access_logs(days: int = 30, keys: int = 10) -> pd.DataFrame:
    """
    Generate synthetic API request logs with realistic daily/weekly patterns.

    Args:
        days: Number of historical days to simulate.
        keys: Number of distinct cache keys to generate.

    Returns:
        DataFrame with columns ['timestamp', 'cache_key'], sorted by timestamp.
    """
    logger.info(
        "Generating access logs: days=%d, keys=%d", days, keys
    )
    start_date = datetime.now() - timedelta(days=days)
    timestamps, key_names = [], []

    for i in range(keys):
        base_pop = np.random.uniform(0.5, 1.5)
        key_label = f"user:{i + 1}:data"
        key_count = 0

        for hour in range(24 * days):
            current_time = start_date + timedelta(hours=hour)
            hour_of_day = hour % 24

            # Daily pattern: peaks at 09:00 and 14:00
            daily_factor = (
                1
                + 0.8 * np.exp(-((hour_of_day - 9) ** 2) / 10)
                + 0.6 * np.exp(-((hour_of_day - 14) ** 2) / 8)
            )

            # Weekly pattern: Mon–Fri higher than Sat–Sun
            weekly_factor = 1.5 if current_time.weekday() < 5 else 0.4

            rate = base_pop * daily_factor * weekly_factor
            count = np.random.poisson(rate * 3)

            if count > 0:
                for _ in range(count):
                    minute_offset = np.random.randint(0, 60)
                    timestamps.append(current_time + timedelta(minutes=minute_offset))
                    key_names.append(key_label)
                key_count += count

        logger.debug(
            "  Key '%s' (base_pop=%.2f): %d total access events", key_label, base_pop, key_count
        )

    df = pd.DataFrame({"timestamp": timestamps, "cache_key": key_names})
    df = df.sort_values("timestamp").reset_index(drop=True)
    logger.info(
        "Access log generation complete: %d rows across %d keys.", len(df), keys
    )
    return df


def generate_db_updates(days: int = 30, keys: int = 10) -> pd.DataFrame:
    """
    Simulate database write events used by the Volatility Engine.

    Each key is assigned a random update frequency class:
    - Very low  (0.01 updates/hr) — nearly static data
    - Low       (0.05 updates/hr)
    - Moderate  (0.10 updates/hr)
    - High      (0.50 updates/hr) — very volatile data

    Args:
        days: Number of historical days to simulate.
        keys: Number of distinct cache keys.

    Returns:
        DataFrame with columns ['timestamp', 'cache_key'].
    """
    logger.info(
        "Generating DB update logs: days=%d, keys=%d", days, keys
    )
    start_date = datetime.now() - timedelta(days=days)
    timestamps, key_names = [], []
    freq_choices = [0.01, 0.05, 0.1, 0.5]

    for i in range(keys):
        update_freq = np.random.choice(freq_choices)
        key_label = f"user:{i + 1}:data"
        update_count = 0

        for hour in range(24 * days):
            current_time = start_date + timedelta(hours=hour)
            if np.random.random() < update_freq:
                timestamps.append(current_time)
                key_names.append(key_label)
                update_count += 1

        logger.debug(
            "  Key '%s' (freq=%.2f): %d DB updates", key_label, update_freq, update_count
        )

    df = pd.DataFrame({"timestamp": timestamps, "cache_key": key_names})
    logger.info("DB update generation complete: %d rows.", len(df))
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from config import cfg

    logger.info("=== Synthetic Data Generation Start ===")

    logger.info("--- Access Logs ---")
    access_df = generate_access_logs(days=30, keys=10)
    access_df.to_csv(cfg.RAW_LOGS_PATH, index=False)
    logger.info("Saved access logs → %s", cfg.RAW_LOGS_PATH)

    logger.info("--- DB Update Logs ---")
    db_df = generate_db_updates(days=30, keys=10)
    db_df.to_csv(cfg.DB_UPDATES_PATH, index=False)
    logger.info("Saved DB updates → %s", cfg.DB_UPDATES_PATH)

    logger.info(
        "=== Done: %d access events | %d DB updates ===",
        len(access_df),
        len(db_df),
    )