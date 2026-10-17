"""Offline Belady bounds on object hit ratio (unit-size objects, equal capacity in objects).

Two variants, both with bypass (an object is not admitted if every resident is needed sooner):

* ``plain``: classic Belady that ignores writes for hit accounting, but still tracks versions so
  the stale reads it would serve are counted.  Context only.
* ``ttl_constrained`` (this project's own construction, A-9): the next-use of an object is its
  next access only if that access is a READ before the key's next write; otherwise it has no
  future value.  A write evicts the cached copy, so it serves zero stale reads by construction
  and is an upper bound on the hit ratio of any zero-stale policy with the same capacity in
  objects.

Unit-size objects are an approximation (variable-size OPT is NP-hard, Berger et al.); the
capacity in objects is ``total cache bytes / mean unique-object size``.  Reported as a bound on
OBJECT hit ratio only, never as a byte bound.
"""
from __future__ import annotations

import heapq

import numpy as np

from ..trace.oracle import Oracle
from ..trace.record import NO_FUTURE_IDX, Trace

_INF = np.iinfo(np.int64).max


def _next_read_index(trace: Trace) -> np.ndarray:
    n = len(trace)
    nxt = np.full(n, _INF, dtype=np.int64)
    last: dict[int, int] = {}
    keys, wr = trace.key.tolist(), trace.is_write.tolist()
    for i in range(n - 1, -1, -1):
        k = keys[i]
        if k in last:
            nxt[i] = last[k]
        if not wr[i]:
            last[k] = i
    return nxt


def belady_bound(trace: Trace, orc: Oracle, capacity_objects: int, start: int, end: int,
                 measure_from: int, ttl_constrained: bool,
                 next_read: np.ndarray | None = None) -> dict:
    """Run the offline policy on requests [start, end); count reads from ``measure_from``."""
    C = max(1, int(capacity_objects))
    keys = trace.key.tolist()
    wr = trace.is_write.tolist()
    na = orc.next_access_idx.tolist()
    nw = orc.next_write_idx.tolist()
    nr = (next_read if next_read is not None else _next_read_index(trace)).tolist()
    cache: dict[int, int] = {}                 # key -> next_use (global index) it was filed under
    cver: dict[int, int] = {}
    ver: dict[int, int] = {}
    heap: list[tuple[int, int]] = []           # (-next_use, key), lazily invalidated
    reads = hits = stale = 0
    for i in range(start, end):
        k = keys[i]
        if wr[i]:
            ver[k] = ver.get(k, 0) + 1
            if ttl_constrained:
                pass
            continue
        if ttl_constrained:
            a, w = na[i], nw[i]
            nu = a if (a != NO_FUTURE_IDX and a < w) else _INF
            if nu != _INF and wr[nu]:
                nu = _INF                      # next access is a write -> value dies first
        else:
            nu = nr[i]
        measuring = i >= measure_from
        if measuring:
            reads += 1
        if k in cache:
            if measuring:
                hits += 1
                if not ttl_constrained and cver[k] != ver.get(k, 0):
                    stale += 1
            cache[k] = nu
            heapq.heappush(heap, (-nu, k))
            continue
        if nu == _INF:
            continue                           # no future use: bypass
        if len(cache) >= C:
            while heap:                        # farthest VALID resident, via the lazy heap
                negnu, v = heap[0]
                if v in cache and cache[v] == -negnu:
                    break
                heapq.heappop(heap)
            negnu, v = heap[0]
            if -negnu <= nu:
                continue                       # every resident is needed no later: bypass
            heapq.heappop(heap)
            del cache[v]
        cache[k] = nu
        cver[k] = ver.get(k, 0)
        heapq.heappush(heap, (-nu, k))
    return {"reads": reads, "hits": hits, "stale": stale,
            "ohr": hits / reads if reads else 0.0,
            "stale_rate": stale / reads if reads else 0.0}
