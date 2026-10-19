"""
simulate_trace.py — Cache Trace Simulation & Adaptive TTL Benchmark.

Replays Twitter cluster traces (cluster001.txt or cluster002.txt) against the
Adaptive TTL Engine, tracking cache hit ratios, hot-key triggers, and volatility
adjustments compared against a fixed-TTL baseline.

Usage:
    # Fast in-process simulation on 100,000 requests:
    python src/simulate_trace.py --trace data/cluster001.txt --limit 100000

    # Simulation against live Flask API:
    python src/simulate_trace.py --trace data/cluster001.txt --api http://localhost:5001 --limit 5000
"""

import argparse
import logging
import sys
import time
from pathlib import Path

import pandas as pd
import requests

# Add src/ to path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import cfg
from fusion_engine import TTLFusionEngine
from hotkey_detector import HotKeyDetector
from volatility import VolatilityEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("simulate_trace")

TRACE_COLUMNS = [
    "timestamp_sec",
    "cache_key",
    "key_size",
    "val_size",
    "client_id",
    "op",
    "ttl",
]


class CacheSimulator:
    def __init__(self, name: str):
        self.name = name
        self.cache: dict[str, float] = {}  # key -> expiry_time (seconds)
        self.hits = 0
        self.misses = 0

    def get(self, key: str, current_time: float) -> bool:
        expiry = self.cache.get(key)
        if expiry is not None and expiry > current_time:
            self.hits += 1
            return True
        self.misses += 1
        return False

    def put(self, key: str, ttl_seconds: float, current_time: float):
        self.cache[key] = current_time + ttl_seconds

    def invalidate(self, key: str):
        self.cache.pop(key, None)

    @property
    def hit_ratio(self) -> float:
        total = self.hits + self.misses
        return (self.hits / total * 100.0) if total > 0 else 0.0


def run_simulation(
    trace_path: Path,
    limit_rows: int | None = 100000,
    fixed_ttl: int = 300,
    api_url: str | None = None,
):
    logger.info("==================================================")
    logger.info("  Adaptive TTL Engine — Cluster Trace Simulator   ")
    logger.info("==================================================")
    logger.info("Trace file: %s", trace_path)
    logger.info("Row limit: %s", limit_rows or "All")
    logger.info("Mode: %s", f"HTTP API ({api_url})" if api_url else "Direct Engine (In-Process)")

    df = pd.read_csv(
        trace_path,
        header=None,
        names=TRACE_COLUMNS,
        nrows=limit_rows,
        dtype={"timestamp_sec": int, "cache_key": str, "op": str},
    )
    logger.info("Loaded %d requests for simulation.", len(df))

    # Initialize Simulators
    adaptive_sim = CacheSimulator("Adaptive TTL")
    fixed_sim = CacheSimulator(f"Fixed TTL ({fixed_ttl}s)")

    # Engines for direct in-process mode
    hotkey_detector = HotKeyDetector(
        threshold=cfg.HOTKEY_THRESHOLD,
        window_seconds=cfg.HOTKEY_WINDOW_SECONDS,
    )
    fusion_engine = TTLFusionEngine(min_ttl=cfg.MIN_TTL, max_ttl=cfg.MAX_TTL)

    # Statistics
    hot_key_triggers = 0
    ttl_values = []
    t_start = time.perf_counter()

    for idx, row in df.iterrows():
        t = float(row["timestamp_sec"])
        key = str(row["cache_key"])
        op = str(row["op"]).lower()

        # Write/Update operations invalidate cache
        if op in ["add", "set", "cas", "replace", "delete"]:
            adaptive_sim.invalidate(key)
            fixed_sim.invalidate(key)
            continue

        # Read operations (get / gets)
        # 1. Fixed TTL Cache check
        if not fixed_sim.get(key, t):
            fixed_sim.put(key, fixed_ttl, t)

        # 2. Adaptive TTL Cache check
        is_hit = adaptive_sim.get(key, t)
        if not is_hit:
            # Miss: query TTL Engine
            if api_url:
                try:
                    resp = requests.post(f"{api_url}/api/v1/predict/{key}", timeout=2.0)
                    if resp.status_code == 200:
                        data = resp.json()
                        pred_ttl = data.get("suggested_ttl", cfg.DEFAULT_TTL)
                        if data.get("is_hot"):
                            hot_key_triggers += 1
                    else:
                        pred_ttl = cfg.DEFAULT_TTL
                except Exception:
                    pred_ttl = cfg.DEFAULT_TTL
            else:
                # Direct in-process logic
                is_hot = hotkey_detector.record_request(key)
                if is_hot:
                    hot_key_triggers += 1
                    pred_ttl = cfg.MAX_TTL
                else:
                    # Default baseline popularity score
                    pred_ttl = int(fusion_engine.calculate_ttl(0.7, 0.0, is_hot))

            ttl_values.append(pred_ttl)
            adaptive_sim.put(key, pred_ttl, t)

        if (idx + 1) % 25000 == 0:
            logger.info("Processed %d / %d requests...", idx + 1, len(df))

    elapsed = time.perf_counter() - t_start
    avg_ttl = (sum(ttl_values) / len(ttl_values)) if ttl_values else 0

    logger.info("==================================================")
    logger.info("               SIMULATION RESULTS                 ")
    logger.info("==================================================")
    logger.info("Requests Processed:        %d", len(df))
    logger.info("Execution Time:            %.2f s (%.0f req/s)", elapsed, len(df) / elapsed)
    logger.info("--------------------------------------------------")
    logger.info("Fixed TTL (%ds) Hit Ratio:  %.2f%% (Hits: %d, Misses: %d)",
                fixed_ttl, fixed_sim.hit_ratio, fixed_sim.hits, fixed_sim.misses)
    logger.info("Adaptive TTL Hit Ratio:    %.2f%% (Hits: %d, Misses: %d)",
                adaptive_sim.hit_ratio, adaptive_sim.hits, adaptive_sim.misses)
    logger.info("Hit Ratio Delta:           %+0.2f%%", adaptive_sim.hit_ratio - fixed_sim.hit_ratio)
    logger.info("--------------------------------------------------")
    logger.info("Hot-Key Triggers Detected: %d", hot_key_triggers)
    logger.info("Average Suggested TTL:     %.1f seconds", avg_ttl)
    logger.info("==================================================")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulate cluster trace against Adaptive TTL Engine")
    parser.add_argument(
        "--trace",
        type=str,
        default=str(cfg.DATA_DIR / "cluster001.txt"),
        help="Path to cluster trace file",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100000,
        help="Number of requests to simulate (default: 100000, 0 for all)",
    )
    parser.add_argument(
        "--fixed-ttl",
        type=int,
        default=300,
        help="Baseline fixed TTL in seconds for comparison (default: 300)",
    )
    parser.add_argument(
        "--api",
        type=str,
        default=None,
        help="Optional HTTP URL of running API (e.g. http://localhost:5001)",
    )

    args = parser.parse_args()
    limit = None if args.limit == 0 else args.limit
    run_simulation(
        trace_path=Path(args.trace),
        limit_rows=limit,
        fixed_ttl=args.fixed_ttl,
        api_url=args.api,
    )
