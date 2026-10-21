"""Pluggable base eviction policies for the simulator tiers (R-B8, R-S10; Addendum M11-E, E1).

The default ``sampled_lru`` (Redis-style approximate LRU with the eviction-priority multiplier) lives in
:meth:`Simulator._pick_victim` and is NOT touched.  The policies here replace it per tier:

* ``lru``    exact LRU (hit moves to the MRU end).
* ``fifo``   insertion order, hits ignored.
* ``sieve``  Zhang et al., NSDI'24: FIFO queue + a hand that sweeps from the oldest to the newest object; an
             object with its visited bit set gets the bit cleared and is retained (lazy promotion), the first
             unvisited object is evicted (quick demotion); the hand continues from the evicted object's
             neighbour, newly inserted objects go to the head and are NOT visited.
* ``s3fifo`` Yang et al., SOSP'23: a small FIFO (10% of the tier's bytes), a main FIFO and a ghost FIFO of keys
             evicted from the small queue (bounded by 90% of the tier's bytes).  Frequency is capped at 3.
             Eviction from S: freq > 1 -> promote to M (frequency reset), else evict and remember in the ghost.
             Eviction from M: freq > 0 -> reinsert with freq - 1, else evict.  An insertion whose key is in the
             ghost goes straight to M.  (Promotion/reset details follow the paper's description; stated as a
             reading, not as the reference implementation.)

They ignore the eviction-priority action dimension.  Sizes are bytes; one copy per key per tier.  Every method
is O(1) amortised.  Interface used by the engine: ``on_insert(c)``, ``on_hit(c)``, ``on_remove(c)`` (every
removal: eviction, expiry, invalidation), ``victim() -> copy``.
"""
from __future__ import annotations

from collections import OrderedDict


class LRUEvictor:
    def __init__(self, cap: int):
        self.q: OrderedDict[int, object] = OrderedDict()

    def on_insert(self, c) -> None:
        self.q[c.key] = c

    def on_hit(self, c) -> None:
        self.q.move_to_end(c.key)

    def on_remove(self, c) -> None:
        self.q.pop(c.key, None)

    def victim(self):
        return next(iter(self.q.values()))


class FIFOEvictor(LRUEvictor):
    def on_hit(self, c) -> None:
        pass


class SieveEvictor:
    """Doubly linked list by key: ``newer``/``older`` pointers; head = newest, tail = oldest."""

    def __init__(self, cap: int):
        self.obj: dict[int, object] = {}
        self.newer: dict[int, int | None] = {}
        self.older: dict[int, int | None] = {}
        self.visited: dict[int, bool] = {}
        self.head: int | None = None
        self.tail: int | None = None
        self.hand: int | None = None

    def on_insert(self, c) -> None:
        k = c.key
        self.obj[k] = c
        self.visited[k] = False
        self.newer[k], self.older[k] = None, self.head
        if self.head is not None:
            self.newer[self.head] = k
        self.head = k
        if self.tail is None:
            self.tail = k

    def on_hit(self, c) -> None:
        self.visited[c.key] = True

    def on_remove(self, c) -> None:
        k = c.key
        if k not in self.obj:
            return
        n, o = self.newer.pop(k), self.older.pop(k)
        if self.hand == k:
            self.hand = n                       # the hand moves toward newer objects
        if n is not None:
            self.older[n] = o
        else:
            self.head = o
        if o is not None:
            self.newer[o] = n
        else:
            self.tail = n
        del self.obj[k], self.visited[k]

    def victim(self):
        k = self.hand if self.hand is not None else self.tail
        while self.visited[k]:
            self.visited[k] = False
            nk = self.newer[k]
            k = nk if nk is not None else self.tail
        self.hand = k                           # on_remove(k) will advance it to k's newer neighbour
        return self.obj[k]


class S3FIFOEvictor:
    SMALL_FRAC = 0.10
    GHOST_FRAC = 0.90
    FREQ_CAP = 3

    def __init__(self, cap: int):
        self.cap = int(cap)
        self.small: OrderedDict[int, object] = OrderedDict()
        self.main: OrderedDict[int, object] = OrderedDict()
        self.freq: dict[int, int] = {}
        self.small_bytes = 0
        self.ghost: OrderedDict[int, int] = OrderedDict()       # key -> size
        self.ghost_bytes = 0

    def _ghost_add(self, k: int, size: int) -> None:
        if k in self.ghost:
            self.ghost_bytes -= self.ghost.pop(k)
        self.ghost[k] = size
        self.ghost_bytes += size
        limit = self.GHOST_FRAC * self.cap
        while self.ghost_bytes > limit and self.ghost:
            _, s = self.ghost.popitem(last=False)
            self.ghost_bytes -= s

    def on_insert(self, c) -> None:
        k = c.key
        self.freq[k] = 0
        if k in self.ghost:
            self.ghost_bytes -= self.ghost.pop(k)
            self.main[k] = c
        else:
            self.small[k] = c
            self.small_bytes += c.size

    def on_hit(self, c) -> None:
        k = c.key
        if k in self.freq:
            self.freq[k] = min(self.freq[k] + 1, self.FREQ_CAP)

    def on_remove(self, c) -> None:
        k = c.key
        if k in self.small:
            del self.small[k]
            self.small_bytes -= c.size
        else:
            self.main.pop(k, None)
        self.freq.pop(k, None)

    def victim(self):
        while True:
            use_small = self.small and (self.small_bytes >= self.SMALL_FRAC * self.cap or not self.main)
            if use_small:
                k, c = next(iter(self.small.items()))
                if self.freq[k] > 1:                              # promote S -> M
                    del self.small[k]
                    self.small_bytes -= c.size
                    self.main[k] = c
                    self.freq[k] = 0
                    continue
                self._ghost_add(k, c.size)
                return c
            k, c = next(iter(self.main.items()))
            if self.freq[k] > 0:                                  # M: reinsert with freq - 1
                self.freq[k] -= 1
                self.main.move_to_end(k)
                continue
            return c


EVICTORS = {"lru": LRUEvictor, "fifo": FIFOEvictor, "sieve": SieveEvictor, "s3fifo": S3FIFOEvictor}
DEFAULT = "sampled_lru"
