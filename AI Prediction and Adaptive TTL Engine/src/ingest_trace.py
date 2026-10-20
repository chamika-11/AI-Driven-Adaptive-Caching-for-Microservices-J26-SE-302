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
import json
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

    # Identify active keys from real Twitter cluster operations:
    # 1. Top 5 pure read-intensive keys
    # 2. Top 5 keys that have BOTH frequent reads AND writes (for realistic EWMA volatility testing)
    read_counts = reads_df["cache_key"].value_counts()
    write_counts = writes_df["cache_key"].value_counts()

    common_keys = set(read_counts.index).intersection(set(write_counts.index))
    
    # 5 top read keys
    pure_read_keys = [k for k in read_counts.index if k not in common_keys][:5]
    if len(pure_read_keys) < 5:
        pure_read_keys = list(read_counts.index[:5])
        
    # 5 active read + write keys
    active_rw_keys = list(writes_df[writes_df["cache_key"].isin(common_keys)]["cache_key"].value_counts().index[:5])
    
    selected_raw_keys = pure_read_keys + active_rw_keys
    # Ensure exactly top_keys unique keys
    seen = set()
    final_selected = []
    for k in selected_raw_keys:
        if k not in seen:
            seen.add(k)
            final_selected.append(k)
    # Fill remaining from read_counts if needed
    for k in read_counts.index:
        if len(final_selected) >= top_keys:
            break
        if k not in seen:
            seen.add(k)
            final_selected.append(k)

    key_aliases = {k: f"twitter:key:{idx + 1}" for idx, k in enumerate(final_selected)}
    reverse_map = {
        f"twitter:key:{idx + 1}": {
            "raw_key": k,
            "reads": int(read_counts.get(k, 0)),
            "writes": int(write_counts.get(k, 0)),
            "type": "read_heavy" if write_counts.get(k, 0) == 0 else "volatile_rw"
        }
        for idx, k in enumerate(final_selected)
    }

    # Save mapping for transparent Twitter data provenance
    map_path = output_raw_logs.parent / "twitter_key_map.json"
    with open(map_path, "w") as f:
        json.dump(reverse_map, f, indent=2)
    logger.info("Saved Twitter trace key provenance map -> %s", map_path)

    for idx, k in enumerate(final_selected, 1):
        info = reverse_map[f"twitter:key:{idx}"]
        logger.info(
            "  #%d: twitter:key:%d (%s) -> %d reads, %d writes [%s]",
            idx, idx, k[:18] + "...", info["reads"], info["writes"], info["type"]
        )

    # Filter reads and writes to the selected keys and map to canonical twitter aliases
    filtered_reads = reads_df[reads_df["cache_key"].isin(final_selected)].copy()
    filtered_writes = writes_df[writes_df["cache_key"].isin(final_selected)].copy()

    filtered_reads["cache_key"] = filtered_reads["cache_key"].map(key_aliases)
    filtered_writes["cache_key"] = filtered_writes["cache_key"].map(key_aliases)

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

    # If filtered_writes has no updates for some keys, add baseline write entry
    if len(db_updates) == 0:
        logger.warning("No writes captured; generating minimal baseline writes.")
        db_updates = pd.DataFrame([{"timestamp": base_time, "cache_key": f"twitter:key:{i+1}"} for i in range(top_keys)])

    # Save exclusively from Twitter cluster data
    output_raw_logs.parent.mkdir(parents=True, exist_ok=True)
    raw_logs.to_csv(output_raw_logs, index=False)
    logger.info("Saved %d rows exclusively from Twitter trace to: %s", len(raw_logs), output_raw_logs)

    output_db_updates.parent.mkdir(parents=True, exist_ok=True)
    db_updates.to_csv(output_db_updates, index=False)
    logger.info("Saved %d rows exclusively from Twitter trace to: %s", len(db_updates), output_db_updates)

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
