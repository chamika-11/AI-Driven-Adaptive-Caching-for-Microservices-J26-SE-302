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


# ---- registry ------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Spec:
    name: str
    family: str
    policy_class: str                     # heuristic | bound
    make: Callable[["object"], object]    # (EvalContext) -> policy


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
    if include_bounds:
        for p in (REDIS, BOTH):
            out.append(Spec(f"zerostale_oracle_ttl:{PLACEMENTS[p]}", "oracle_ttl", "bound",
                            lambda c, p=p: ZeroStaleOracleTTL(c.oracle.next_write_ts, p)))
        out.append(Spec("belady_ttl_constrained", "belady", "bound", None))     # offline, see bounds.py
        out.append(Spec("belady_plain", "belady", "bound", None))
    return out
