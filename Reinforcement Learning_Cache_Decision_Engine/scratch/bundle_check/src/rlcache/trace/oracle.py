"""Two-pass oracle annotation (R-D9).

For every request ``i`` with key ``k``:

    next_access_idx[i] = smallest j > i with key[j] == k            (any operation)
    next_write_idx[i]  = smallest j > i with key[j] == k and write  (a source mutation)

``NO_FUTURE_IDX`` (int64 max) marks "never again".  These arrays use FUTURE information: they
feed Belady, oracle TTL and TTL-constrained Belady (own construction, A-9) and are BOUNDS, never
features (R-D8, R-P8).  The module lives apart from the feature code so that an import-level
audit can prove the simulator's observation path never touches it.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .record import NO_FUTURE_IDX, Trace


@dataclass(frozen=True)
class Oracle:
    next_access_idx: np.ndarray     # int64, NO_FUTURE_IDX if none
    next_write_idx: np.ndarray      # int64, NO_FUTURE_IDX if none
    next_access_ts: np.ndarray      # float64, +inf if none
    next_write_ts: np.ndarray       # float64, +inf if none


def annotate_oracle(tr: Trace) -> Oracle:
    n = len(tr)
    nxt_a = np.full(n, NO_FUTURE_IDX, dtype=np.int64)
    nxt_w = np.full(n, NO_FUTURE_IDX, dtype=np.int64)
    last_access: dict[int, int] = {}
    last_write: dict[int, int] = {}
    keys = tr.key.tolist()
    wr = tr.is_write.tolist()
    for i in range(n - 1, -1, -1):           # single reverse pass computes both annotations
        k = keys[i]
        j = last_access.get(k)
        if j is not None:
            nxt_a[i] = j
        j = last_write.get(k)
        if j is not None:
            nxt_w[i] = j
        last_access[k] = i
        if wr[i]:
            last_write[k] = i
    ts = tr.ts
    inf = np.inf
    na_ts = np.where(nxt_a != NO_FUTURE_IDX, ts[np.minimum(nxt_a, n - 1)], inf)
    nw_ts = np.where(nxt_w != NO_FUTURE_IDX, ts[np.minimum(nxt_w, n - 1)], inf)
    return Oracle(nxt_a, nxt_w, na_ts, nw_ts)


def time_to_next_write(tr: Trace, orc: Oracle, idx: int) -> float:
    """Seconds from request ``idx`` until the next write to its key (inf if none)."""
    return float(orc.next_write_ts[idx] - tr.ts[idx])
