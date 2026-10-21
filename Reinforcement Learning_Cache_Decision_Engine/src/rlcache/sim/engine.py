"""Event-driven two-tier cache simulator (M4; R-S1, R-S2, R-S4..S7, R-S10..S14, R-S19).

No RL in here.  A pluggable ``policy`` is asked for a flat action only at DECISION POINTS (a read
that misses both tiers and starts a backend fetch).  Every decision creates an :class:`Insertion`
that owns up to two cache copies and is closed EXACTLY ONCE, carrying the raw accumulators the
reward computer (M5) needs.

Model summary
-------------
* Lookup order L1 -> L2 -> backend.  A read is classified fresh / stale / miss (R-S12): a cached
  copy is fresh iff its version equals the key's current source version.
* A write is a source-of-truth mutation (A-1): it bumps the key's version and invalidates cached
  copies according to :class:`~rlcache.config.StalenessConfig` (C-6, D-20).
* A miss starts a backend fetch occupying ``[t, t + backend_latency]``.  The value becomes visible
  only when the fetch completes, so reads of the same key inside the window are real misses
  (stampede, C-20).  The decision is taken at fetch START; the value fetched carries the source
  version at fetch start, so a write during the fetch makes it stale on arrival.
* Expiry is exact: a min-heap event closes a copy at ``expires_at`` even if never read (R-S7).
* Eviction: sampled-LRU over ``eviction_samples`` random residents, score
  ``idle_time / priority_multiplier``, highest evicted (D-13, A-6).
* One insertion per key at a time (asserted in invariant mode).

Closing rule (D-24): an insertion closes when its LAST copy is gone (or it is rejected /
truncated / hard-capped).  ``first_reason`` records the first terminal event.
"""
from __future__ import annotations

import heapq
import math
import time as _time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol

import numpy as np

from ..actions import decode_action
from ..config import CacheConfig, Config
from ..trace.record import Trace
from . import eviction as _evict

# close reasons
R_EXPIRY, R_EVICTION, R_INVAL, R_HARDCAP, R_REJECTED, R_TRUNC = (
    "expiry", "eviction", "invalidation", "hardcap", "rejected", "truncated")
CLOSE_REASONS = (R_EXPIRY, R_EVICTION, R_INVAL, R_HARDCAP, R_REJECTED, R_TRUNC)

_EV_MATERIALIZE, _EV_EXPIRE, _EV_L1_INVAL, _EV_HARDCAP = 0, 1, 2, 3
_L1, _L2 = 0, 1


def resolve_capacities(trace: Trace, cache: CacheConfig) -> tuple[int, int]:
    """(l1_bytes, l2_bytes).  Footprint-relative sizing overrides the absolute default."""
    if cache.l2_footprint_frac is not None:
        l2 = max(1, int(trace.footprint_bytes() * cache.l2_footprint_frac))
    else:
        l2 = cache.l2_capacity_bytes
    l1 = max(1, int(l2 * cache.l1_fraction_of_l2))
    return l1, l2


class Policy(Protocol):
    def decide(self, ctx: "DecisionContext") -> int: ...


class DecisionContext:
    """Everything a policy may look at when a miss needs a placement decision."""
    __slots__ = ("idx", "ts", "key", "size", "sim")

    def __init__(self, idx: int, ts: float, key: int, size: int, sim: "Simulator"):
        self.idx, self.ts, self.key, self.size, self.sim = idx, ts, key, size, sim


class Insertion:
    """One decision and everything it caused until it closed."""
    __slots__ = (
        "id", "key", "idx", "t_decision", "action", "ttl_s", "placement", "priority", "size",
        "fetch_version", "t_materialize", "write_during_fetch_t", "live_copies", "n_copies_made",
        "closed", "close_time", "close_reason", "first_reason", "first_close_time", "measured",
        "hits_l1", "hits_l2", "fresh", "stale", "stale_age_sum", "stale_cost_sum", "lat_score_sum",
        "byte_seconds", "concurrent", "payload", "evictions", "expirations")

    def __init__(self, id_: int, key: int, idx: int, t: float, action: int, size: int,
                 version: int, measured: bool):
        a = decode_action(action)
        self.id, self.key, self.idx, self.t_decision = id_, key, idx, t
        self.action, self.ttl_s, self.placement, self.priority = (
            action, float(a.ttl_s), a.placement, a.priority)
        self.size, self.fetch_version = size, version
        self.t_materialize = math.nan
        self.write_during_fetch_t: Optional[float] = None
        self.live_copies = 0
        self.n_copies_made = 0
        self.closed = False
        self.close_time = math.nan
        self.close_reason = ""
        self.first_reason = ""
        self.first_close_time = math.nan
        self.measured = measured
        self.hits_l1 = self.hits_l2 = self.fresh = self.stale = 0
        self.stale_age_sum = self.stale_cost_sum = self.lat_score_sum = 0.0
        self.byte_seconds = 0.0
        self.concurrent = 1            # fetches for this key overlapping this one, incl. itself
        self.payload: Any = None       # opaque slot for the M5 state snapshot
        self.evictions = self.expirations = 0

    @property
    def hits(self) -> int:
        return self.hits_l1 + self.hits_l2

    @property
    def lifetime_s(self) -> float:
        return self.close_time - self.t_decision


class _Copy:
    __slots__ = ("key", "tier", "ins", "version", "size", "t_in", "expires_at", "last_access",
                 "mult", "stale_since", "alive", "pos")

    def __init__(self, key, tier, ins, version, size, t_in, expires_at, mult, stale_since):
        self.key, self.tier, self.ins, self.version, self.size = key, tier, ins, version, size
        self.t_in, self.expires_at, self.last_access = t_in, expires_at, t_in
        self.mult, self.stale_since, self.alive, self.pos = mult, stale_since, True, -1


class _Tier:
    __slots__ = ("id", "cap", "used", "entries", "order")

    def __init__(self, id_: int, cap: int):
        self.id, self.cap, self.used = id_, cap, 0
        self.entries: dict[int, _Copy] = {}
        self.order: list[_Copy] = []          # for O(1) random sampling (swap-remove)

    def add(self, c: _Copy) -> None:
        c.pos = len(self.order)
        self.order.append(c)
        self.entries[c.key] = c
        self.used += c.size

    def remove(self, c: _Copy) -> None:
        last = self.order[-1]
        self.order[c.pos] = last
        last.pos = c.pos
        self.order.pop()
        del self.entries[c.key]
        self.used -= c.size
        c.pos = -1


@dataclass
class Metrics:
    """Counted events over the MEASURED window (R-S12..S14).  Warm-up is excluded."""
    n_reads: int = 0
    fresh_l1: int = 0
    fresh_l2: int = 0
    stale_l1: int = 0
    stale_l2: int = 0
    n_miss: int = 0
    n_writes: int = 0
    n_decisions: int = 0
    backend_fetches: int = 0           # one per read that reaches the backend
    backend_writes: int = 0
    bytes_read: int = 0
    bytes_hit: int = 0
    cap_evictions: int = 0
    ttl_expirations: int = 0
    invalidations: int = 0
    rejected: int = 0
    concurrent_fetches: int = 0        # extra overlapping fetches for an already-fetching key
    # utility ingredients over the MEASURED window only (the scalar U of M6; warm-up excluded)
    lat_score_hits: float = 0.0        # sum of exp(-L/L0) over served reads
    lat_score_miss: float = 0.0        # sum of exp(-L_backend/L0) over missing reads
    stale_cost: float = 0.0            # sum of min(1, age / ttl_chosen) over stale reads
    stale_ages: list = field(default_factory=list)
    throughput: list = field(default_factory=list)       # (request_index, requests/s)

    @property
    def n_fresh(self) -> int:
        return self.fresh_l1 + self.fresh_l2

    @property
    def n_stale(self) -> int:
        return self.stale_l1 + self.stale_l2

    @property
    def n_hit(self) -> int:
        return self.n_fresh + self.n_stale

    def ohr(self) -> float:
        return self.n_hit / self.n_reads if self.n_reads else 0.0

    def stale_read_rate(self) -> float:
        return self.n_stale / self.n_reads if self.n_reads else 0.0


class Simulator:
    def __init__(self, trace: Trace, cfg: Config, policy: Policy, *,
                 l1_capacity_bytes: int | None = None, l2_capacity_bytes: int | None = None,
                 seed: int = 0, check_invariants: bool = False, keep_closed: bool = True,
                 sink: Callable[[Insertion], None] | None = None,
                 record_latencies: bool = True, observer: Any = None):
        self.trace, self.cfg, self.policy = trace, cfg, policy
        l1, l2 = resolve_capacities(trace, cfg.cache)
        self.l1 = _Tier(_L1, l1 if l1_capacity_bytes is None else int(l1_capacity_bytes))
        self.l2 = _Tier(_L2, l2 if l2_capacity_bytes is None else int(l2_capacity_bytes))
        self.seed = seed
        ss = np.random.SeedSequence(seed)
        s_evict, s_stale = ss.spawn(2)
        self._rng_evict = np.random.default_rng(s_evict)
        n = len(trace)
        # Common random numbers: the staleness rolls of write #i do not depend on the policy.
        u = np.random.default_rng(s_stale).random((n, 2)) if n else np.empty((0, 2))
        self._u_bypass, self._u_inv = u[:, 0].tolist(), u[:, 1].tolist()
        self._ts = trace.ts.tolist()
        self._key = trace.key.tolist()
        self._size = trace.size.tolist()
        self._is_write = trace.is_write.tolist()
        self.ver = [0] * trace.n_keys
        self.last_write_t = [math.nan] * trace.n_keys
        self.fetching: dict[int, Insertion] = {}
        self._heap: list = []
        self._seq = 0
        self._inflight: list[float] = []              # fetch end times (min-heap)
        self.open: dict[int, Insertion] = {}
        self.closed: list[Insertion] = []
        self.keep_closed = keep_closed
        self.sink = sink
        self._on_close = getattr(policy, "on_close", None)
        self._on_decision = getattr(policy, "on_decision", None)
        self._observer = observer
        self.n_closed = 0
        self.n_created = 0
        self.metrics = Metrics()
        self.latencies: list[float] = [] if record_latencies else None  # type: ignore
        self.check_invariants_flag = check_invariants
        lat = cfg.latency
        self._l1_s, self._l2_s, self._bk_s = lat.l1_us * 1e-6, lat.l2_us * 1e-6, lat.backend_us * 1e-6
        self._l0_us = lat.l0_us
        sig = float(lat.backend_sigma)
        if sig > 0.0:                                   # LogNormal with mean 1, fixed per key
            z = np.random.default_rng(lat.seed).standard_normal(trace.n_keys)
            scale = np.exp(sig * z - 0.5 * sig * sig)
        else:
            scale = np.ones(trace.n_keys)
        self.key_backend_s: list[float] = (self._bk_s * scale).tolist()
        self._lat_score_l1 = math.exp(-lat.l1_us / lat.l0_us)
        self._lat_score_l2 = math.exp(-lat.l2_us / lat.l0_us)
        self._st = cfg.staleness
        self._mult = cfg.cache.priority_mult
        self._samples = max(1, cfg.cache.eviction_samples)
        kind = cfg.cache.base_eviction
        if kind == _evict.DEFAULT:
            self._ev = None
        elif kind in _evict.EVICTORS:                   # Addendum M11-E (E1); ignores the priority dimension
            self._ev = {_L1: _evict.EVICTORS[kind](self.l1.cap), _L2: _evict.EVICTORS[kind](self.l2.cap)}
        else:
            raise ValueError(f"unknown base_eviction {kind!r}")
        self._promote = cfg.cache.promote_on_l2_hit
        self._hard_cap = cfg.cache.hard_cap_s
        self.now = 0.0
        self._measuring = True
        self.idx = 0

    # ---- public state accessors (used by the M5 feature tracker) --------------------------
    def utilisation(self) -> float:
        """Total used bytes / total configured bytes (equal-total-capacity accounting)."""
        return (self.l1.used + self.l2.used) / (self.l1.cap + self.l2.cap)

    def tier_utilisation(self) -> tuple[float, float]:
        return self.l1.used / self.l1.cap, self.l2.used / self.l2.cap

    def inflight(self, t: float) -> int:
        h = self._inflight
        while h and h[0] <= t:
            heapq.heappop(h)
        return len(h)

    # ---- event plumbing -------------------------------------------------------------------------
    def _push(self, time_: float, kind: int, obj: Any, extra: Any = None) -> None:
        self._seq += 1
        heapq.heappush(self._heap, (time_, self._seq, kind, obj, extra))

    def _advance(self, t: float) -> None:
        h = self._heap
        while h and h[0][0] <= t:
            tm, _, kind, obj, extra = heapq.heappop(h)
            if kind == _EV_MATERIALIZE:
                self._materialize(obj, tm)
            elif kind == _EV_EXPIRE:
                if obj.alive:
                    self._remove_copy(obj, tm, R_EXPIRY)
            elif kind == _EV_L1_INVAL:
                if obj.alive:                      # same copy still resident
                    self._remove_copy(obj, tm, R_INVAL)
            else:                                  # hard cap
                if not obj.closed:
                    self._hard_cap_close(obj, tm)

    # ---- copy / insertion lifecycle --------------------------------------------------------------
    def _close(self, ins: Insertion, t: float, reason: str) -> None:
        assert not ins.closed, "insertion closed twice"
        ins.closed, ins.close_time, ins.close_reason = True, t, reason
        if not ins.first_reason:
            ins.first_reason, ins.first_close_time = reason, t
        self.open.pop(ins.id, None)
        self.n_closed += 1
        if self.keep_closed:
            self.closed.append(ins)
        if self.sink is not None:
            self.sink(ins)
        if self._on_close is not None:
            self._on_close(ins)

    def _remove_copy(self, c: _Copy, t: float, reason: str) -> None:
        tier = self.l1 if c.tier == _L1 else self.l2
        tier.remove(c)
        if self._ev is not None:
            self._ev[tier.id].on_remove(c)
        c.alive = False
        ins = c.ins
        ins.byte_seconds += c.size * (t - c.t_in)
        ins.live_copies -= 1
        if not ins.first_reason:
            ins.first_reason, ins.first_close_time = reason, t
        m = self.metrics
        if self._measuring:
            if reason == R_EVICTION:
                m.cap_evictions += 1
            elif reason == R_EXPIRY:
                m.ttl_expirations += 1
            elif reason == R_INVAL:
                m.invalidations += 1
        if reason == R_EVICTION:
            ins.evictions += 1
        elif reason == R_EXPIRY:
            ins.expirations += 1
        if ins.live_copies == 0 and not ins.closed:
            self._close(ins, t, reason)

    def _hard_cap_close(self, ins: Insertion, t: float) -> None:
        for tier in (self.l1, self.l2):
            c = tier.entries.get(ins.key)
            if c is not None and c.ins is ins:
                self._remove_copy(c, t, R_HARDCAP)
        if not ins.closed:
            self._close(ins, t, R_HARDCAP)

    def _pick_victim(self, tier: _Tier, t: float) -> _Copy:
        if self._ev is not None:
            return self._ev[tier.id].victim()
        order = tier.order
        n = len(order)
        if n <= self._samples:
            cand = order
        else:
            cand = [order[j] for j in self._rng_evict.integers(0, n, self._samples).tolist()]
        best, best_s = cand[0], -1.0
        for c in cand:
            s = (t - c.last_access + 1e-6) / c.mult        # idle time, divided by protection
            if s > best_s:
                best, best_s = c, s
        return best

    def _insert_copy(self, ins: Insertion, tier: _Tier, t: float, expires_at: float,
                     stale_since: Optional[float]) -> bool:
        size = ins.size
        if size > tier.cap:
            return False
        while tier.used + size > tier.cap:
            self._remove_copy(self._pick_victim(tier, t), t, R_EVICTION)
        c = _Copy(ins.key, tier.id, ins, ins.fetch_version, size, t, expires_at,
                  self._mult[ins.priority], stale_since)
        tier.add(c)
        if self._ev is not None:
            self._ev[tier.id].on_insert(c)
        ins.live_copies += 1
        ins.n_copies_made += 1
        self._push(expires_at, _EV_EXPIRE, c)
        return True

    def _materialize(self, ins: Insertion, t: float) -> None:
        """The backend fetch completed: the value becomes visible per the chosen placement."""
        self.fetching.pop(ins.key, None)
        ins.t_materialize = t
        went_stale = self.ver[ins.key] != ins.fetch_version
        if went_stale and self._st.mode == "perfect":
            # D-25: "perfect invalidation" must also cover the fetch/write race, otherwise the
            # stale-read rate would not be identically 0 and the gate would be untestable.
            if self._measuring:
                self.metrics.invalidations += 1
            self._close(ins, t, R_INVAL)
            return
        stale_since = ins.write_during_fetch_t if went_stale else None
        exp = t + ins.ttl_s
        ok = False
        if ins.placement in (0, 2):                      # local / both
            ok |= self._insert_copy(ins, self.l1, t, exp, stale_since)
        if ins.placement in (1, 2):                      # redis / both
            ok |= self._insert_copy(ins, self.l2, t, exp, stale_since)
        if not ok:
            if self._measuring:
                self.metrics.rejected += 1
            self._close(ins, t, R_REJECTED)
            return
        if ins.ttl_s + self.key_backend_s[ins.key] > self._hard_cap:   # only then can it bind
            self._push(ins.t_decision + self._hard_cap, _EV_HARDCAP, ins)

    # ---- request handlers --------------------------------------------------------------------------
    def _write(self, i: int, t: float, k: int) -> None:
        self.ver[k] += 1
        self.last_write_t[k] = t
        if self._measuring:
            self.metrics.n_writes += 1
            self.metrics.backend_writes += 1
        ins = self.fetching.get(k)
        if ins is not None and ins.write_during_fetch_t is None:
            ins.write_during_fetch_t = t
        c1, c2 = self.l1.entries.get(k), self.l2.entries.get(k)
        for c in (c1, c2):
            if c is not None and c.stale_since is None:
                c.stale_since = t                        # its version just became superseded
        if c1 is None and c2 is None:
            return
        st = self._st
        if st.mode == "ttl_only":
            return
        if st.mode == "perfect":
            for c in (c1, c2):
                if c is not None:
                    self._remove_copy(c, t, R_INVAL)
            return
        # lossy (primary): bypass skips both tiers; L2 sync; L1 with prob p_inv after d_inv
        if self._u_bypass[i] < st.p_bypass:
            return
        if c2 is not None:
            self._remove_copy(c2, t, R_INVAL)
        if c1 is not None and self._u_inv[i] < st.p_inv_l1:
            if st.d_inv_l1_s <= 0.0:
                self._remove_copy(c1, t, R_INVAL)
            else:
                self._push(t + st.d_inv_l1_s, _EV_L1_INVAL, c1)

    def _serve(self, c: _Copy, t: float, k: int, tier_id: int) -> None:
        ins = c.ins
        c.last_access = t
        if self._ev is not None:
            self._ev[tier_id].on_hit(c)
        fresh = c.version == self.ver[k]
        if tier_id == _L1:
            ins.hits_l1 += 1
            ins.lat_score_sum += self._lat_score_l1
        else:
            ins.hits_l2 += 1
            ins.lat_score_sum += self._lat_score_l2
        m = self.metrics
        if fresh:
            ins.fresh += 1
            age = 0.0
        else:
            age = t - c.stale_since                      # type: ignore[operator]
            ins.stale += 1
            ins.stale_age_sum += age
            ins.stale_cost_sum += min(1.0, age / ins.ttl_s)
        if self._measuring:
            m.n_reads += 1
            m.bytes_read += c.size
            m.bytes_hit += c.size
            m.lat_score_hits += self._lat_score_l1 if tier_id == _L1 else self._lat_score_l2
            if not fresh:
                m.stale_cost += min(1.0, age / ins.ttl_s)
            if fresh:
                if tier_id == _L1:
                    m.fresh_l1 += 1
                else:
                    m.fresh_l2 += 1
            else:
                if tier_id == _L1:
                    m.stale_l1 += 1
                else:
                    m.stale_l2 += 1
                m.stale_ages.append(age)
            if self.latencies is not None:
                self.latencies.append(self._l1_s if tier_id == _L1 else self._l2_s)

    def _read(self, i: int, t: float, k: int):
        """True = served from cache, False = miss with a fetch already in flight (no decision),
        None = a miss that needs a placement decision (the caller must :meth:`commit` one)."""
        c = self.l1.entries.get(k)
        if c is not None:
            self._serve(c, t, k, _L1)
            return True
        c = self.l2.entries.get(k)
        if c is not None:
            self._serve(c, t, k, _L2)
            if self._promote and k not in self.l1.entries:
                self._promote_copy(c, t)
            return True
        # ---- miss: goes to the backend ----------------------------------------------------------
        m = self.metrics
        size = self._size[i]
        if self._measuring:
            m.n_reads += 1
            m.n_miss += 1
            m.backend_fetches += 1
            m.bytes_read += size
            m.lat_score_miss += math.exp(-self.key_backend_s[k] * 1e6 / self._l0_us)
            if self.latencies is not None:
                self.latencies.append(self.key_backend_s[k])
        live = self.fetching.get(k)
        if live is not None:                             # fetch already in flight: stampede
            live.concurrent += 1
            if self._measuring:
                m.concurrent_fetches += 1
            heapq.heappush(self._inflight, t + self.key_backend_s[k])
            return False
        return None

    def _create_insertion(self, i: int, t: float, k: int, size: int, action: int) -> Insertion:
        self.n_created += 1
        ins = Insertion(self.n_created, k, i, t, action, size, self.ver[k], self._measuring)
        self.open[ins.id] = ins
        self.fetching[k] = ins
        if self._measuring:
            self.metrics.n_decisions += 1
        end = t + self.key_backend_s[k]
        heapq.heappush(self._inflight, end)
        self._push(end, _EV_MATERIALIZE, ins)
        if self._on_decision is not None:
            self._on_decision(ins)
        return ins

    def _promote_copy(self, src: _Copy, t: float) -> None:
        """R-S2 promotion: an L1 copy of the same insertion that inherits version and expiry."""
        ins = src.ins
        size = ins.size
        if size > self.l1.cap:
            return
        while self.l1.used + size > self.l1.cap:
            self._remove_copy(self._pick_victim(self.l1, t), t, R_EVICTION)
        c = _Copy(ins.key, _L1, ins, src.version, size, t, src.expires_at, src.mult,
                  src.stale_since)
        self.l1.add(c)
        if self._ev is not None:
            self._ev[_L1].on_insert(c)
        ins.live_copies += 1
        ins.n_copies_made += 1
        self._push(c.expires_at, _EV_EXPIRE, c)

    # ---- driver ---------------------------------------------------------------------------------
    # The loop is resumable so an external controller (the RL trainer, the Gymnasium adapter) can
    # be handed each decision point:  begin() ; while (ctx := next_decision()): commit(action).
    def begin(self, start: int = 0, end: int | None = None, measure_from: int | None = None) -> None:
        n = len(self._ts)
        self._cur = start
        self._end = n if end is None else end
        self._mf = start if measure_from is None else measure_from
        self._pending: tuple | None = None
        self._tp_start = start
        self._t_wall = _time.perf_counter()
        self._last_t = self._ts[start] if start < n else 0.0
        self.done = False

    def next_decision(self) -> DecisionContext | None:
        """Process requests until a miss needs a decision (returned) or the slice ends (None)."""
        if self._pending is not None:
            raise RuntimeError("commit() the pending decision before asking for the next one")
        ts, keys, isw = self._ts, self._key, self._is_write
        while self._cur < self._end:
            i = self._cur
            t = ts[i]
            k = keys[i]
            self._last_t = t
            self.idx, self.now = i, t
            self._measuring = i >= self._mf
            self._advance(t)
            if isw[i]:
                self._write(i, t, k)
                self._after(i, t, k, True, None)
                continue
            r = self._read(i, t, k)
            if r is None:
                self._pending = (i, t, k, self._size[i])
                return DecisionContext(i, t, k, self._size[i], self)
            self._after(i, t, k, False, r)
        if not self.done:
            self.finalize(self._last_t)
            self.done = True
            if self.check_invariants_flag:
                self.check_invariants()
        return None

    def commit(self, action: int) -> Insertion:
        """Apply the placement decision for the pending miss and finish that request."""
        if self._pending is None:
            raise RuntimeError("no pending decision")
        i, t, k, size = self._pending
        self._pending = None
        ins = self._create_insertion(i, t, k, size, int(action))
        self._after(i, t, k, False, False)
        return ins

    def _after(self, i: int, t: float, k: int, is_write: bool, hit) -> None:
        if self._observer is not None:
            self._observer.on_request(i, t, k, is_write, hit)
        if self.check_invariants_flag and (i & 63) == 0:
            self.check_invariants()
        self._cur = i + 1
        every = 50_000
        if (i - self._tp_start) % every == every - 1:
            now = _time.perf_counter()
            self.metrics.throughput.append((i, every / max(now - self._t_wall, 1e-9)))
            self._t_wall = now

    def run(self, start: int = 0, end: int | None = None, measure_from: int | None = None) -> Metrics:
        """Drive the whole slice with the constructor's policy (decide() per decision point)."""
        self.begin(start, end, measure_from)
        while True:
            ctx = self.next_decision()
            if ctx is None:
                break
            self.commit(int(self.policy.decide(ctx)))
        return self.metrics

    def finalize(self, t: float) -> None:
        """Close every still-open insertion as 'truncated' (end of run), exactly once."""
        self._measuring = False
        self._advance(t)
        for ins in list(self.open.values()):
            for tier in (self.l1, self.l2):
                c = tier.entries.get(ins.key)
                if c is not None and c.ins is ins:
                    tier.remove(c)
                    c.alive = False
                    ins.byte_seconds += c.size * (t - c.t_in)
                    ins.live_copies -= 1
            self.fetching.pop(ins.key, None)
            if not ins.closed:
                self._close(ins, t, R_TRUNC)

    # ---- invariants (tests + debug mode) -----------------------------------------------------------
    def check_invariants(self) -> None:
        seen_keys: set[int] = set()
        for tier in (self.l1, self.l2):
            assert 0 <= tier.used <= tier.cap, f"tier {tier.id} used {tier.used} > cap {tier.cap}"
            assert tier.used == sum(c.size for c in tier.order)
            assert len(tier.order) == len(tier.entries)
            for j, c in enumerate(tier.order):
                assert c.pos == j and c.alive and tier.entries[c.key] is c
                assert not c.ins.closed or c.ins.close_reason == R_TRUNC
        for ins in self.open.values():
            assert not ins.closed
            assert ins.key not in seen_keys, "two open insertions for one key"
            seen_keys.add(ins.key)
            n = sum(1 for tier in (self.l1, self.l2)
                    if (c := tier.entries.get(ins.key)) is not None and c.ins is ins)
            assert n == ins.live_copies, (n, ins.live_copies)
        assert self.n_created == self.n_closed + len(self.open)
