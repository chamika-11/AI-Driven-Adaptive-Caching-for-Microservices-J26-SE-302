"""
ingest_trace.py — Convert Twitter Cache Traces into TTL Engine Datasets.

Parses cluster001.txt or cluster002.txt and generates:
  - data/raw_logs.csv    (Read/GET operations for access frequency & popularity)
  - data/db_updates.csv  (Write/SET/ADD operations for volatility tracking)

Usage:
    python src/ingest_trace.py --file data/cluster001.txt --top-keys 10
    python src/ingest_trace.py --file data/cluster002.txt --top-keys 10 --time-scale 1800
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

# Add src/ to path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import cfg

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("ingest_trace")

# Twitter Memcached Trace Column Schema
TRACE_COLUMNS = [
    "timestamp_sec",
    "cache_key",
    "key_size",
    "val_size",
    "client_id",
    "op",
    "ttl",
]


def ingest_trace(
    trace_path: Path,
    top_keys: int = 10,
    time_scale: int = 1800,
    limit_rows: int | None = None,
    output_raw_logs: Path = cfg.RAW_LOGS_PATH,
    output_db_updates: Path = cfg.DB_UPDATES_PATH,
):
    """
    Ingest a Twitter cluster trace file and extract raw_logs.csv and db_updates.csv.

    Args:
        trace_path: Path to cluster001.txt or cluster002.txt
        top_keys: Number of top most-requested keys to retain for training models.
        time_scale: Seconds to expand 1 trace second into (default 1800s = 30 min per trace sec,
                    ensuring enough temporal span across days for time-series features).
        limit_rows: Optional limit on rows to read for fast prototyping.
        output_raw_logs: Destination path for raw_logs.csv
        output_db_updates: Destination path for db_updates.csv
    """
    logger.info("Reading trace file from: %s", trace_path)
    if not trace_path.exists():
        raise FileNotFoundError(f"Trace file not found: {trace_path}")

    df = pd.read_csv(
        trace_path,
        header=None,
        names=TRACE_COLUMNS,
        nrows=limit_rows,
        dtype={"timestamp_sec": int, "cache_key": str, "op": str},
    )
    logger.info("Loaded %d rows from trace.", len(df))

    # Standardize operations:
    # Read operations: 'get', 'gets'
    # Write / Update operations: 'add', 'set', 'cas', 'replace'
    df["op"] = df["op"].str.lower()
    reads_df = df[df["op"].isin(["get", "gets"])].copy()
    writes_df = df[df["op"].isin(["add", "set", "cas", "replace", "append", "prepend"])].copy()

    logger.info("Total Read ops (get/gets): %d", len(reads_df))
    logger.info("Total Write/Update ops (add/set/cas): %d", len(writes_df))

    # Identify the Top-K most active keys
    key_counts = reads_df["cache_key"].value_counts()
    selected_keys = set(key_counts.head(top_keys).index)
    logger.info(
        "Filtered to Top %d most active keys (covering %d / %d reads, %.1f%%):",
        top_keys,
        key_counts.head(top_keys).sum(),
        len(reads_df),
        (key_counts.head(top_keys).sum() / len(reads_df)) * 100,
    )
    for idx, (k, cnt) in enumerate(key_counts.head(top_keys).items(), 1):
        logger.info("  #%d: %s (requests: %d)", idx, k, cnt)

    # Filter reads and writes to the selected keys
    filtered_reads = reads_df[reads_df["cache_key"].isin(selected_keys)].copy()
    filtered_writes = writes_df[writes_df["cache_key"].isin(selected_keys)].copy()

    # Map relative trace seconds to synthetic ISO datetimes
    base_time = datetime(2026, 7, 1, 0, 0, 0)
    logger.info(
        "Converting timestamps with time_scale=%ds (1 trace sec = %d seconds)",
        time_scale,
        time_scale,
    )

    filtered_reads["timestamp"] = filtered_reads["timestamp_sec"].apply(
        lambda s: base_time + timedelta(seconds=int(s * time_scale))
    )
    filtered_writes["timestamp"] = filtered_writes["timestamp_sec"].apply(
        lambda s: base_time + timedelta(seconds=int(s * time_scale))
    )

    # Prepare standard columns
    raw_logs = filtered_reads[["timestamp", "cache_key"]].sort_values("timestamp")
    db_updates = filtered_writes[["timestamp", "cache_key"]].sort_values("timestamp")

    # If filtered_writes has no updates for some keys, add minimal baseline updates
    if len(db_updates) == 0:
        logger.warning(
            "Selected top keys had no write operations in trace window. Synthesizing low-rate writes."
        )
        synthetic_records = []
        for k in selected_keys:
            synthetic_records.append({"timestamp": base_time, "cache_key": k})
        db_updates = pd.DataFrame(synthetic_records)

    # Save to CSV
    output_raw_logs.parent.mkdir(parents=True, exist_ok=True)
    raw_logs.to_csv(output_raw_logs, index=False)
    logger.info("Saved %d rows to: %s", len(raw_logs), output_raw_logs)

    output_db_updates.parent.mkdir(parents=True, exist_ok=True)
    db_updates.to_csv(output_db_updates, index=False)
    logger.info("Saved %d rows to: %s", len(db_updates), output_db_updates)

    logger.info("Trace ingestion complete!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ingest Twitter cache trace (cluster001.txt / cluster002.txt) for TTL Engine"
    )
    parser.add_argument(
        "--file",
        type=str,
        default=str(cfg.DATA_DIR / "cluster001.txt"),
        help="Path to trace file (cluster001.txt or cluster002.txt)",
    )
    parser.add_argument(
        "--top-keys",
        type=int,
        default=10,
        help="Number of top frequent keys to extract for model training (default: 10)",
    )
    parser.add_argument(
        "--time-scale",
        type=int,
        default=1800,
        help="Scaling factor in seconds for trace timestamps (default: 1800)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional row limit to read from trace file",
    )

    args = parser.parse_args()
    ingest_trace(
        trace_path=Path(args.file),
        top_keys=args.top_keys,
        time_scale=args.time_scale,
        limit_rows=args.limit,
    )
