"""In-memory trace representation shared by the real-trace parser and the synthetic generator.

A :class:`Trace` is a struct of numpy arrays, one entry per request, ordered by time.  Keys are
dense integer ids; the string key never leaves the parser.

Operation semantics (R-D3, A-1):  ``get``/``gets`` are READS.  Every other operation is a WRITE,
i.e. a source-of-truth mutation behind the cache that creates a new *version* of the key.  The
simulator derives stale reads by comparing a cached copy's version with the key's current version.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

OPS: tuple[str, ...] = ("get", "gets", "set", "add", "replace", "cas", "append", "prepend",
                        "delete", "incr", "decr")
OP_CODE: dict[str, int] = {n: i for i, n in enumerate(OPS)}
READ_CODES = frozenset({OP_CODE["get"], OP_CODE["gets"]})
WRITE_OPS = frozenset({"set", "add", "replace", "cas", "append", "prepend", "incr", "decr",
                       "delete"})                                           # R-D3
OP_DELETE = OP_CODE["delete"]

NO_FUTURE_IDX = np.iinfo(np.int64).max     # oracle sentinel: key never accessed/written again
DEFAULT_OBJECT_SIZE = 1024                 # causal fallback when no size has been seen yet


@dataclass
class Trace:
    ts: np.ndarray            # float64 seconds, non-decreasing
    key: np.ndarray           # int64 dense key id in [0, n_keys)
    size: np.ndarray          # int32 effective object size in bytes (causally forward-filled)
    client: np.ndarray        # int32 anonymised client / frontend id
    op: np.ndarray            # int8 code into OPS
    ttl: np.ndarray           # int32 client-set TTL on writes, 0 elsewhere (label only)
    n_keys: int
    source: str = "synthetic"                  # "synthetic" | "twitter_real"
    name: str = "trace"
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        n = len(self.ts)
        for nm in ("key", "size", "client", "op", "ttl"):
            if len(getattr(self, nm)) != n:
                raise ValueError(f"column {nm} length {len(getattr(self, nm))} != {n}")
        if n and self.key.max() >= self.n_keys:
            raise ValueError("key id >= n_keys")

    def __len__(self) -> int:
        return len(self.ts)

    # ---- derived views -------------------------------------------------------------------
    @property
    def is_write(self) -> np.ndarray:
        return self.op >= OP_CODE["set"]

    @property
    def is_read(self) -> np.ndarray:
        return self.op < OP_CODE["set"]

    @property
    def duration_s(self) -> float:
        return float(self.ts[-1] - self.ts[0]) if len(self) else 0.0

    def slice(self, a: int, b: int) -> "Trace":
        """Contiguous request-index slice [a, b) (a view; key ids stay global)."""
        if not 0 <= a <= b <= len(self):
            raise ValueError(f"bad slice [{a}, {b}) of {len(self)}")
        return Trace(self.ts[a:b], self.key[a:b], self.size[a:b], self.client[a:b],
                     self.op[a:b], self.ttl[a:b], self.n_keys, self.source,
                     f"{self.name}[{a}:{b}]", dict(self.meta))

    def with_spread_timestamps(self) -> "Trace":
        """Spread requests sharing an identical timestamp evenly inside their time slot.

        Real traces have 1-second resolution, so hundreds of requests can share one ``ts``.  The
        simulator models an 8 ms backend fetch window, and with exact ties every same-second read
        of a key would look concurrent.  Row ``j`` of an ``m``-row tie group moves to
        ``ts + (j + 0.5) / m * min(1, gap_to_next_distinct_ts)``; relative order and the overall
        timeline are preserved.  Row order is unchanged (a stable, order-preserving remap).
        """
        n = len(self)
        if n == 0:
            return self
        uniq, start, cnt = np.unique(self.ts, return_index=True, return_counts=True)
        gap = np.empty(len(uniq))
        gap[:-1] = np.minimum(np.diff(uniq), 1.0)
        gap[-1] = 1.0
        grp = np.repeat(np.arange(len(uniq)), cnt)            # ts is sorted -> contiguous groups
        within = np.arange(n) - start[grp]
        new_ts = self.ts + (within + 0.5) / cnt[grp] * gap[grp]
        return Trace(new_ts, self.key, self.size, self.client, self.op, self.ttl, self.n_keys,
                     self.source, self.name, dict(self.meta, spread_timestamps=True))

    def footprint_bytes(self) -> int:
        """Total bytes of the unique-object working set (max size observed per key)."""
        if not len(self):
            return 0
        per_key = np.zeros(self.n_keys, dtype=np.int64)
        np.maximum.at(per_key, self.key, self.size)
        return int(per_key.sum())

    def n_unique_keys(self) -> int:
        return int(np.unique(self.key).size)

    def validate(self) -> None:
        if len(self) and np.any(np.diff(self.ts) < 0):
            raise ValueError("timestamps are not non-decreasing")
        if np.any(self.size <= 0):
            raise ValueError("object sizes must be positive")
        if np.any(self.op < 0) or np.any(self.op >= len(OPS)):
            raise ValueError("op code out of range")
        if np.any(self.ttl[self.is_read] != 0):
            raise ValueError("reads must carry TTL 0")

    def op_counts(self) -> dict[str, int]:
        c = np.bincount(self.op, minlength=len(OPS))
        return {OPS[i]: int(c[i]) for i in range(len(OPS)) if c[i]}

    def write_fraction(self) -> float:
        return float(self.is_write.mean()) if len(self) else 0.0
