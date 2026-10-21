"""results.csv schema (D-17, R-E12).

One row = one (policy config x seed x trace x capacity x split) evaluation.  All tables and
figures are generated from this file only.  Cumulative reward is deliberately NOT a column that
is comparable across policies (MD 'Metrics'); it is stored as ``train_return`` for diagnostics.
"""
from __future__ import annotations

import csv
import math
import os
from pathlib import Path
from typing import Iterable, Mapping

# (name, kind) -- kind in {"str", "int", "float", "bool"}.  "provenance" columns first.
COLUMNS: tuple[tuple[str, str], ...] = (
    # provenance
    ("run_id", "str"), ("config_digest", "str"), ("git_commit", "str"), ("seed", "int"),
    ("data_source", "str"),            # "synthetic" | "twitter_real"  (never blur these)
    ("trace_name", "str"), ("split", "str"),      # train | val | test
    ("policy", "str"), ("policy_class", "str"),   # learned | heuristic | bound
    ("capacity_frac", "float"), ("l1_frac", "float"),
    ("staleness_mode", "str"), ("w_stale", "float"),
    ("predictor_accuracy", "float"),
    # counted events
    ("n_reads", "int"), ("n_fresh", "int"), ("n_stale", "int"), ("n_miss", "int"),
    ("n_writes", "int"), ("n_decisions", "int"),
    # headline metrics
    ("ohr", "float"), ("bhr", "float"), ("stale_read_rate", "float"),
    ("stale_given_hit", "float"), ("stale_age_mean_s", "float"), ("stale_age_p95_s", "float"),
    ("backend_per_1k_reads", "float"),
    ("lat_mean_us", "float"), ("lat_p50_us", "float"), ("lat_p95_us", "float"),
    ("lat_p99_us", "float"), ("lat_p999_us", "float"),
    ("cap_evictions_per_1k", "float"), ("ttl_expirations_per_1k", "float"),
    # decision behaviour
    ("ttl_median_s", "float"), ("over_ttl_frac", "float"), ("ttl_mae_s", "float"),
    ("share_local", "float"), ("share_redis", "float"), ("share_both", "float"),
    ("action_entropy_norm", "float"),
    # scalar used ONLY to select within a baseline family on validation (never a cross-policy
    # headline): U = w_hit*hit + w_lat*exp(-L/L0) - w_stale*min(1, age/ttl), per read
    ("utility", "float"), ("family", "str"),
    # diagnostics only
    ("train_return", "float"), ("throughput_req_per_s", "float"), ("notes", "str"),
)
COLUMN_NAMES: tuple[str, ...] = tuple(n for n, _ in COLUMNS)
_KIND = dict(COLUMNS)

# Metrics that must lie in [0, 1] -- validated on write.
_UNIT_INTERVAL = ("ohr", "bhr", "stale_read_rate", "stale_given_hit", "over_ttl_frac",
                  "share_local", "share_redis", "share_both", "action_entropy_norm")
DATA_SOURCES = ("synthetic", "twitter_real")
SPLITS = ("train", "val", "test")
POLICY_CLASSES = ("learned", "heuristic", "bound")


def _coerce(name: str, value):
    kind = _KIND[name]
    if value is None or value == "":
        return ""
    if kind == "str":
        return str(value)
    if kind == "bool":
        return bool(value)
    if kind == "int":
        return int(value)
    v = float(value)
    if math.isnan(v) and name not in ("notes",):
        return ""
    return v


def validate_row(row: Mapping[str, object]) -> dict[str, object]:
    unknown = set(row) - set(COLUMN_NAMES)
    if unknown:
        raise KeyError(f"unknown results columns: {sorted(unknown)}")
    out = {n: _coerce(n, row.get(n)) for n in COLUMN_NAMES}
    for req in ("run_id", "data_source", "trace_name", "split", "policy", "policy_class"):
        if out[req] == "":
            raise ValueError(f"results row is missing required column {req!r}")
    if out["data_source"] not in DATA_SOURCES:
        raise ValueError(f"data_source must be one of {DATA_SOURCES}")
    if out["split"] not in SPLITS:
        raise ValueError(f"split must be one of {SPLITS}")
    if out["policy_class"] not in POLICY_CLASSES:
        raise ValueError(f"policy_class must be one of {POLICY_CLASSES}")
    for n in _UNIT_INTERVAL:
        v = out[n]
        if v != "" and not (0.0 - 1e-9 <= v <= 1.0 + 1e-9):
            raise ValueError(f"{n}={v} outside [0, 1]")
    counts = [out[k] for k in ("n_fresh", "n_stale", "n_miss", "n_reads")]
    if all(c != "" for c in counts) and counts[0] + counts[1] + counts[2] != counts[3]:
        raise ValueError("fresh + stale + miss must equal n_reads (three-way classification)")
    return out


def append_rows(path: str | os.PathLike, rows: Iterable[Mapping[str, object]]) -> int:
    """Validate and append rows, writing the header if the file is new.  Returns rows written."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = [validate_row(r) for r in rows]
    new = not path.exists() or path.stat().st_size == 0
    with open(path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMN_NAMES)
        if new:
            w.writeheader()
        w.writerows(clean)
    return len(clean)


def read_rows(path: str | os.PathLike) -> list[dict[str, str]]:
    with open(path, "r", newline="", encoding="utf-8") as fh:
        rd = csv.DictReader(fh)
        if tuple(rd.fieldnames or ()) != COLUMN_NAMES:
            raise ValueError("results.csv header does not match the schema")
        return list(rd)
