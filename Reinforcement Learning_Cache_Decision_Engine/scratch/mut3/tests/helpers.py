"""Shared micro-trace builder for the test modules."""
import numpy as np

from rlcache.trace.record import OP_CODE, Trace


def mk(rows, size=100, n_keys=None):
    """rows: (t, key, 'r'|'w'[, size])"""
    ts = [r[0] for r in rows]
    key = [r[1] for r in rows]
    op = [OP_CODE["get"] if r[2] == "r" else OP_CODE["set"] for r in rows]
    sz = [r[3] if len(r) > 3 else size for r in rows]
    n = len(rows)
    return Trace(np.array(ts, float), np.array(key, np.int64), np.array(sz, np.int32),
                 np.zeros(n, np.int32), np.array(op, np.int8), np.zeros(n, np.int32),
                 n_keys or (max(key) + 1))
