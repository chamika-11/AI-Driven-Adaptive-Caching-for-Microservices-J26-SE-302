"""Non-learned baselines (M6; R-B1, R-B3, R-B6) and the zero-stale oracle bound.

Every policy exposes ``decide(ctx) -> flat action`` and (optionally) ``on_close(ins)``.  The
frozen list of points is in docs/PREREGISTRATION.md (M6-3); :func:`registry` builds exactly that
list and nothing else.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from ..actions import decode_action, encode_action, nearest_ttl_idx
from ..config import N_ACTIONS, PLACEMENTS, PRIORITY_LEVELS, TTL_BUCKETS_S
from ..predictor.standin import GapStats, PredictorTables
from ..sim.engine import R_TRUNC, Insertion
from ..sim.policy import FixedActionPolicy, RandomPolicy

REDIS, BOTH = 1, 2
NORMAL = 1
DEFAULT_STAT_TTL_IDX = len(TTL_BUCKETS_S) - 1          # keys with no gap history -> 3600 s


class StatTTLPolicy:
    """TTL = inter-write-gap statistic of the key (fit slice only), snapped to a bucket."""

    def __init__(self, gap_stat: np.ndarray, placement: int):
        self.idx = np.full(len(gap_stat), DEFAULT_STAT_TTL_IDX, dtype=np.int64)
        ok = ~np.isnan(gap_stat)
        self.idx[ok] = [nearest_ttl_idx(float(v)) for v in gap_stat[ok]]
        self.idx = self.idx.tolist()
        self.placement = placement

    def decide(self, ctx) -> int:
        return encode_action(self.placement, self.idx[ctx.key], NORMAL)


class PredTTLPolicy:
    """The predictor's ``predicted_ttl`` snapped to a bucket (R-B6)."""

    def __init__(self, tables: PredictorTables, placement: int):
        self.idx = [nearest_ttl_idx(float(v)) for v in tables.predicted_ttl]
        self.placement = placement

    def decide(self, ctx) -> int:
        return encode_action(self.placement, self.idx[ctx.key], NORMAL)


class AIMDPolicy:
    """Per-key TTL, additive increase on a clean insertion, multiplicative decrease on a stale
    read (R-B3 #4).  Feedback arrives at insertion closure, exactly like the learned agents'."""

    def __init__(self, n_keys: int, alpha_s: float, beta: float, start_s: float = 120.0,
                 placement: int = REDIS):
        self.ttl = [float(start_s)] * n_keys
        self.alpha, self.beta, self.placement = float(alpha_s), float(beta), placement
        self.lo, self.hi = float(TTL_BUCKETS_S[0]), float(TTL_BUCKETS_S[-1])

    def decide(self, ctx) -> int:
        return encode_action(self.placement, nearest_ttl_idx(self.ttl[ctx.key]), NORMAL)

    def on_close(self, ins: Insertion) -> None:
        if ins.close_reason == R_TRUNC:
            return
        k = ins.key
        if ins.stale > 0:
            self.ttl[k] = max(self.lo, self.ttl[k] * self.beta)
        elif ins.hits > 0:
            self.ttl[k] = min(self.hi, self.ttl[k] + self.alpha)


class ZeroStaleOracleTTL:
    """BOUND: largest bucket <= time to the key's next write (5 s if shorter; 3600 s if never
    rewritten).  Uses the future, so it is never a baseline.  Under a finite staleness penalty
    zero staleness is NOT utility-optimal, so this is not an upper bound on U."""

    def __init__(self, next_write_ts: np.ndarray, placement: int):
        self.nw = next_write_ts
        self.placement = placement
        self.edges = np.asarray(TTL_BUCKETS_S, float)

    def decide(self, ctx) -> int:
        tnw = self.nw[ctx.idx] - ctx.ts
        j = int(np.searchsorted(self.edges, tnw, side="right")) - 1
        return encode_action(self.placement, max(j, 0), NORMAL)


# ---- placement-lattice baselines (docs/PREREGISTRATION.md, Addendum M6-B: POST-HOC) -------------
LOCAL = 0
PLACE_TTL_IDX = 3                                       # 600 s for every placement-rule policy


class HashPlacementPolicy:
    """A fixed fraction of keys (stable hash of the key id) go to `local`, the rest to `redis`:
    the simplest way to use L1 and L2 as DISJOINT capacity."""

    def __init__(self, frac: float):
        self.frac = float(frac)

    def decide(self, ctx) -> int:
        h = ((ctx.key * 2654435761) & 0xFFFFFFFF) / 4294967296.0
        return encode_action(LOCAL if h < self.frac else REDIS, PLACE_TTL_IDX, NORMAL)


class SizePlacementPolicy:
    """Objects no larger than ``threshold`` bytes go to `local`, larger ones to `redis`."""

    def __init__(self, threshold: float):
        self.threshold = float(threshold)

    def decide(self, ctx) -> int:
        return encode_action(LOCAL if ctx.size <= self.threshold else REDIS, PLACE_TTL_IDX, NORMAL)


class FreqPlacementPolicy:
    """`local` if the key was requested >= k times among the last ``window`` requests (history
    strictly before the decision request), else `redis`.  Fed through the simulator observer."""

    def __init__(self, k: int, window: int = 1000):
        self.k, self.window = int(k), int(window)
        self._ring: list[int] = []
        self._head = 0
        self._counts: dict[int, int] = {}

    def on_request(self, i, t, key, is_write, hit) -> None:
        if len(self._ring) == self.window:
            old = self._ring[self._head]
            c = self._counts[old] - 1
            if c:
                self._counts[old] = c
            else:
                del self._counts[old]
            self._ring[self._head] = key
        else:
            self._ring.append(key)
        self._head = (self._head + 1) % self.window
        self._counts[key] = self._counts.get(key, 0) + 1

    def decide(self, ctx) -> int:
        local = self._counts.get(ctx.key, 0) >= self.k
        return encode_action(LOCAL if local else REDIS, PLACE_TTL_IDX, NORMAL)


# ---- registry ------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Spec:
    name: str
    family: str
    policy_class: str                     # heuristic | bound
    make: Callable[["object"], object]    # (EvalContext) -> policy
    post_hoc: bool = False                # added after a development result (Addendum M6-B)
    eviction: str = "sampled_lru"         # base eviction of the tiers (Addendum M11-E, E1)


def _fixed_name(a: int) -> str:
    d = decode_action(a)
    return f"fixed:{PLACEMENTS[d.placement]}/{d.ttl_s}s/{PRIORITY_LEVELS[d.priority]}"


def registry(include_bounds: bool = True) -> list[Spec]:
    out: list[Spec] = []
    for a in range(N_ACTIONS):
        out.append(Spec(_fixed_name(a), "fixed", "heuristic", lambda c, a=a: FixedActionPolicy(a)))
    out.append(Spec("random:45", "random", "heuristic", lambda c: RandomPolicy(c.seed)))
    for stat in ("mean", "median", "p10"):
        for p in (REDIS, BOTH):
            out.append(Spec(f"stat_ttl:{stat}/{PLACEMENTS[p]}", "stat_ttl", "heuristic",
                            lambda c, stat=stat, p=p: StatTTLPolicy(getattr(c.gap_stats, stat), p)))
    for p in (REDIS, BOTH):
        out.append(Spec(f"pred_ttl:{PLACEMENTS[p]}", "pred_ttl", "heuristic",
                        lambda c, p=p: PredTTLPolicy(c.predictor, p)))
    for alpha in (60.0, 300.0):
        for beta in (0.5, 0.25):
            out.append(Spec(f"aimd:a{int(alpha)}/b{beta}", "aimd", "heuristic",
                            lambda c, al=alpha, be=beta: AIMDPolicy(c.trace.n_keys, al, be)))
    for f in (0.10, 0.25, 0.50):
        out.append(Spec(f"place_hash:{f:.2f}", "place_hash", "heuristic",
                        lambda c, f=f: HashPlacementPolicy(f), post_hoc=True))
    for q in (25, 50, 75):
        out.append(Spec(f"place_size:p{q}", "place_size", "heuristic",
                        lambda c, q=q: SizePlacementPolicy(
                            float(np.percentile(c.trace.size[:c.splits.fit_end], q))), post_hoc=True))
    for k in (2, 3, 5):
        out.append(Spec(f"place_freq:k{k}", "place_freq", "heuristic",
                        lambda c, k=k: FreqPlacementPolicy(k), post_hoc=True))
    if include_bounds:
        for p in (REDIS, BOTH):
            out.append(Spec(f"zerostale_oracle_ttl:{PLACEMENTS[p]}", "oracle_ttl", "bound",
                            lambda c, p=p: ZeroStaleOracleTTL(c.oracle.next_write_ts, p)))
        out.append(Spec("belady_ttl_constrained", "belady", "bound", None))     # offline, see bounds.py
        out.append(Spec("belady_plain", "belady", "bound", None))
    return out


def s3fifo_reference_registry() -> list[Spec]:
    """Addendum M11-F: static references UNDER S3-FIFO eviction - fixed (redis | both) x TTL {30, 120, 600, 3600} s
    and the size-threshold placement rule."""
    out: list[Spec] = []
    for p in (REDIS, BOTH):
        for ti in (1, 2, 3, 4):
            a = encode_action(p, ti, NORMAL)
            out.append(Spec(f"evict:s3fifo/{PLACEMENTS[p]}/{TTL_BUCKETS_S[ti]}s", "evict", "heuristic",
                            lambda c, a=a: FixedActionPolicy(a), eviction="s3fifo"))
    out.append(Spec("place_size:p25@s3fifo", "place_size", "heuristic",
                    lambda c: SizePlacementPolicy(float(np.percentile(c.trace.size[:c.splits.fit_end], 25))),
                    eviction="s3fifo"))
    return out


def eviction_registry() -> list[Spec]:
    """Addendum M11-E (E1): fixed (placement, 3600 s, normal) under exact LRU / FIFO / SIEVE / S3-FIFO.
    Kept apart from :func:`registry`, whose 71 points are frozen (M6-3)."""
    ttl_idx = len(TTL_BUCKETS_S) - 1
    out: list[Spec] = []
    for pol in ("lru", "fifo", "sieve", "s3fifo"):
        for p in (REDIS, BOTH):
            a = encode_action(p, ttl_idx, NORMAL)
            out.append(Spec(f"evict:{pol}/{PLACEMENTS[p]}/{TTL_BUCKETS_S[ttl_idx]}s", "evict", "heuristic",
                            lambda c, a=a: FixedActionPolicy(a), eviction=pol))
    return out
