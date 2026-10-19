"""
preprocess.py — Raw Log Aggregation & Feature Engineering.

Reads raw_logs.csv, aggregates into 5-minute buckets per cache key, and
engineers three families of features:

  1. Cyclical  — sine/cosine encoding of hour-of-day and day-of-week.
  2. Lag       — request counts at t-1 (5 min), t-6 (30 min), t-12 (1 hr).
  3. Rolling   — 6-period (30-min) rolling mean and standard deviation.

Output is saved to processed_features.csv for use by train_models.py.
"""

import logging
import sys

import numpy as np
import pandas as pd

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("preprocess")


# ─────────────────────────────────────────────────────────────────────────────
# Core Functions
# ─────────────────────────────────────────────────────────────────────────────

def aggregate_access_logs(raw_df: pd.DataFrame) -> pd.DataFrame:
    """
    Group raw access logs into 5-minute time buckets per cache key.

    Args:
        raw_df: DataFrame with columns ['timestamp', 'cache_key'].

    Returns:
        DataFrame with columns ['bucket', 'cache_key', 'request_count'],
        including zero-filled rows for buckets with no activity.
    """
    logger.info("Aggregating %d raw log rows into 5-min buckets...", len(raw_df))

    df = raw_df.copy()
    df["bucket"] = df["timestamp"].dt.floor("5min")

    # Count requests per (bucket, key) pair
    grouped = (
        df.groupby(["bucket", "cache_key"])
        .size()
        .reset_index(name="request_count")
    )

    # Build the full cartesian product of all buckets × all keys and zero-fill
    all_buckets = pd.date_range(
        start=df["bucket"].min(), end=df["bucket"].max(), freq="5min"
    )
    all_keys = df["cache_key"].unique()

    logger.info(
        "  %d unique buckets × %d unique keys = %d rows in full grid",
        len(all_buckets),
        len(all_keys),
        len(all_buckets) * len(all_keys),
    )

    full_index = pd.MultiIndex.from_product(
        [all_buckets, all_keys], names=["bucket", "cache_key"]
    )
    full_df = (
        grouped.set_index(["bucket", "cache_key"])
        .reindex(full_index, fill_value=0)
        .reset_index()
    )

    logger.info("Aggregation complete: %d rows produced.", len(full_df))
    return full_df


def create_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Engineer cyclical, lag, and rolling statistical features.

    Args:
        df: Aggregated DataFrame from `aggregate_access_logs`.

    Returns:
        Enriched DataFrame with all feature columns appended.
    """
    logger.info("Engineering features on %d rows...", len(df))
    df = df.copy()

    # ── 1. Cyclical Time Encoding ────────────────────────────────────────────
    logger.info("  Step 1/3 — Cyclical encoding (hour sin/cos, dow sin/cos)")
    df["hour"] = df["bucket"].dt.hour
    df["day_of_week"] = df["bucket"].dt.dayofweek

    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)
    df["dow_sin"]  = np.sin(2 * np.pi * df["day_of_week"] / 7)
    df["dow_cos"]  = np.cos(2 * np.pi * df["day_of_week"] / 7)

    # Sort so shifts/rolling are applied in chronological order per key
    df = df.sort_values(["cache_key", "bucket"]).reset_index(drop=True)

    # ── 2. Lag Features ──────────────────────────────────────────────────────
    logger.info("  Step 2/3 — Lag features (t-1, t-6, t-12)")
    df["t_minus_1"]  = df.groupby("cache_key")["request_count"].shift(1)   # 5 min
    df["t_minus_6"]  = df.groupby("cache_key")["request_count"].shift(6)   # 30 min
    df["t_minus_12"] = df.groupby("cache_key")["request_count"].shift(12)  # 1 hour

    # ── 3. Rolling Statistics ────────────────────────────────────────────────
    logger.info("  Step 3/3 — Rolling stats (mean, std over 6 periods = 30 min)")
    df["rolling_mean_6"] = (
        df.groupby("cache_key")["request_count"]
        .rolling(6)
        .mean()
        .reset_index(level=0, drop=True)
    )
    df["rolling_std_6"] = (
        df.groupby("cache_key")["request_count"]
        .rolling(6)
        .std()
        .reset_index(level=0, drop=True)
    )

    # Fill NaNs introduced by shifts and rolling at the start of each series
    df = df.fillna(0)

    logger.info("Feature engineering complete. Columns: %s", list(df.columns))
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from config import cfg

    logger.info("=== Preprocessing Pipeline Start ===")
    logger.info("Reading raw logs from: %s", cfg.RAW_LOGS_PATH)

    raw = pd.read_csv(cfg.RAW_LOGS_PATH, parse_dates=["timestamp"])
    logger.info("Loaded %d raw log rows.", len(raw))

    logger.info("--- Aggregation ---")
    aggregated = aggregate_access_logs(raw)

    logger.info("--- Feature Engineering ---")
    featured = create_features(aggregated)

    output_path = cfg.PROCESSED_FEATURES_PATH
    featured.to_csv(output_path, index=False)
    logger.info("Saved %d rows of processed features to: %s", len(featured), output_path)
    logger.info("=== Preprocessing Pipeline Complete ===")