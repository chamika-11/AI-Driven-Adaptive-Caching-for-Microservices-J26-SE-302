"""The 19-feature state vector: names, order, blocks, and ONE timestamp convention (INV-1).

Timestamp convention (resolves the 'consistent interpretation and timestamp' requirement):

    A decision is taken at request index ``i`` (time ``t_i``) because that request missed.
    Let ``H_i`` be the history = all requests with index ``< i`` (strictly before the decision
    request).  EVERY feature below is a pure function of

        (H_i, the static attributes of request i's key/object, the cache contents at t_i,
         the frozen predictor tables fitted on the predictor-fit split only).

    * Window features (counts, hit ratio, rate, CoV, top-k share, invalidation rate) are computed
      over ``H_i``; request ``i`` itself is NOT included, not even its miss.
    * ``size`` is the size of the object being cached (known when the backend returns it).
    * ``backend_latency`` is the key's modelled fetch latency (A-4); known after the fetch.
    * ``utilisation`` and ``backend_load`` are read from the simulator at ``t_i``.
    * Predictor outputs (``predicted_ttl``, ``volatility``, ``hot_key``) come from tables frozen
      at the end of the predictor-fit split (R-P3); unseen keys get documented defaults (R-P6).

    Consequence: no feature depends on any request with index > i (R-P8), and the successor
    observation s' (D-9) is built with exactly the same rule at the next decision's index.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from .config import N_FEATURES

BLOCK_KEY: Final = "per_key"
BLOCK_CACHE: Final = "cache_wide"
BLOCK_PRED: Final = "predictor_flag"

# normalisation kinds (R-F20)
NORM_MINMAX_FIXED: Final = "minmax_fixed"      # bounded by construction, no learned stats
NORM_LOG_RUNMAX: Final = "log_over_running_max"
NORM_ZSCORE: Final = "zscore_clip"             # Welford/EMA, clip [-5, 5], frozen at eval


@dataclass(frozen=True)
class FeatureSpec:
    index: int          # 0-based position in the observation vector
    name: str
    block: str
    source: str         # where the raw value comes from
    window: str         # temporal extent, always ending strictly before the decision request
    norm: str
    never_seen: str     # value/sentinel when the quantity is undefined
    requirement: str    # R-F id


FEATURES: tuple[FeatureSpec, ...] = (
    FeatureSpec(0, "log_recency_1", BLOCK_KEY, "key access history", "last access of this key",
                NORM_MINMAX_FIXED, "1.0 (sentinel)", "R-F1"),
    FeatureSpec(1, "log_recency_2", BLOCK_KEY, "key access history", "2nd-last access of this key",
                NORM_MINMAX_FIXED, "1.0 (sentinel)", "R-F2"),
    FeatureSpec(2, "count_10", BLOCK_KEY, "global request ring", "last 10 requests",
                NORM_MINMAX_FIXED, "0.0", "R-F3"),
    FeatureSpec(3, "count_100", BLOCK_KEY, "global request ring", "last 100 requests",
                NORM_MINMAX_FIXED, "0.0", "R-F4"),
    FeatureSpec(4, "count_1000", BLOCK_KEY, "global request ring", "last 1000 requests",
                NORM_MINMAX_FIXED, "0.0", "R-F5"),
    FeatureSpec(5, "edc", BLOCK_KEY, "key access history", "exp. decay, 60 s half-life",
                NORM_LOG_RUNMAX, "0.0", "R-F6"),
    FeatureSpec(6, "size", BLOCK_KEY, "object attribute", "n/a (static)",
                NORM_MINMAX_FIXED, "n/a", "R-F7"),
    FeatureSpec(7, "backend_latency", BLOCK_KEY, "backend model (A-4)", "n/a (per-key constant)",
                NORM_MINMAX_FIXED, "backend mean", "R-F8"),
    FeatureSpec(8, "predicted_ttl", BLOCK_KEY, "frozen predictor table", "predictor-fit split",
                NORM_MINMAX_FIXED, "3600 s (never written)", "R-F9"),
    FeatureSpec(9, "volatility", BLOCK_KEY, "frozen predictor table", "predictor-fit split",
                NORM_MINMAX_FIXED, "0.0", "R-F10"),
    FeatureSpec(10, "utilisation", BLOCK_CACHE, "simulator", "instant t_i (bytes used / cap)",
                NORM_MINMAX_FIXED, "0.0", "R-F11"),
    FeatureSpec(11, "hit_ratio", BLOCK_CACHE, "simulator", "last 1000 read requests",
                NORM_MINMAX_FIXED, "0.0", "R-F12"),
    FeatureSpec(12, "request_rate", BLOCK_CACHE, "global request ring", "last 10 s",
                NORM_LOG_RUNMAX, "0.0", "R-F13"),
    FeatureSpec(13, "rate_cov_10s", BLOCK_CACHE, "global request ring", "10 s window, 1 s bins",
                NORM_MINMAX_FIXED, "0.0", "R-F14"),
    FeatureSpec(14, "rate_cov_300s", BLOCK_CACHE, "global request ring", "300 s window, 10 s bins",
                NORM_MINMAX_FIXED, "0.0", "R-F15"),
    FeatureSpec(15, "top10_share", BLOCK_CACHE, "global request ring", "last 1000 requests",
                NORM_MINMAX_FIXED, "0.0", "R-F16"),
    FeatureSpec(16, "invalidation_rate", BLOCK_CACHE, "global write ring", "last 300 s",
                NORM_LOG_RUNMAX, "0.0", "R-F17"),
    FeatureSpec(17, "backend_load", BLOCK_CACHE, "simulator", "instant t_i (open fetch windows)",
                NORM_MINMAX_FIXED, "0.0", "R-F18"),
    FeatureSpec(18, "hot_key_flag", BLOCK_PRED, "frozen predictor table", "predictor-fit split",
                NORM_MINMAX_FIXED, "0.0", "R-F19"),
)

FEATURE_NAMES: tuple[str, ...] = tuple(f.name for f in FEATURES)
FEATURE_INDEX: dict[str, int] = {f.name: f.index for f in FEATURES}

KEY_BLOCK = slice(0, 10)
CACHE_BLOCK = slice(10, 18)
PRED_BLOCK = slice(18, 19)

# Tabular Q-learning projection (R-L12, C-21): utilisation, hit ratio, count_1000, volatility,
# predicted TTL.  The prototype used [10, 11, 4, 0, 8]; index 0 is log recency, NOT volatility.
TABULAR_FEATURES: tuple[str, ...] = (
    "utilisation", "hit_ratio", "count_1000", "volatility", "predicted_ttl")
TABULAR_FEATURE_IDX: tuple[int, ...] = tuple(FEATURE_INDEX[n] for n in TABULAR_FEATURES)

# Ablation state ladder S0..S5 (R-E9): strict subsets, expressed as feature-name sets.
STATE_LADDER: dict[str, tuple[str, ...]] = {
    "S0": ("utilisation",),
    "S1": ("utilisation", "log_recency_1", "log_recency_2", "count_10", "count_100",
           "count_1000", "edc"),
    "S2": ("utilisation", "log_recency_1", "log_recency_2", "count_10", "count_100",
           "count_1000", "edc", "size"),
    "S3": ("utilisation", "log_recency_1", "log_recency_2", "count_10", "count_100",
           "count_1000", "edc", "size", "volatility"),
    "S4": ("utilisation", "log_recency_1", "log_recency_2", "count_10", "count_100",
           "count_1000", "edc", "size", "volatility", "predicted_ttl", "hot_key_flag"),
    "S5": FEATURE_NAMES,
}


def _self_check() -> None:
    assert len(FEATURES) == N_FEATURES
    assert [f.index for f in FEATURES] == list(range(N_FEATURES))
    assert len(set(FEATURE_NAMES)) == N_FEATURES


_self_check()
