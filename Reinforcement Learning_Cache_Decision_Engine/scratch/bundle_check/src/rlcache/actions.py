"""Flat Discrete(45) joint action codec (INV-2, D-6, C-3).

    a = p * 15 + t * 3 + e        p: placement (0..2), t: ttl bucket (0..4), e: priority (0..2)

Placement is the slowest-varying digit and priority the fastest.  The prototype in the MD used a
different (tier-fastest) order; this module is the single source of truth and the exhaustive
round-trip tests in tests/test_actions.py guard against a silent stride-order bug.
"""
from __future__ import annotations

from typing import NamedTuple

import numpy as np

from .config import (N_ACTIONS, N_PLACE, N_PRIO, N_TTL, PLACEMENTS, PRIORITY_LEVELS,
                      TTL_BUCKETS_S)

_STRIDE_P = N_TTL * N_PRIO      # 15
_STRIDE_T = N_PRIO              # 3

PLACE_LOCAL, PLACE_REDIS, PLACE_BOTH = 0, 1, 2
PRIO_LOW, PRIO_NORMAL, PRIO_HIGH = 0, 1, 2


class Action(NamedTuple):
    placement: int      # index into PLACEMENTS
    ttl_idx: int        # index into TTL_BUCKETS_S
    priority: int       # index into PRIORITY_LEVELS

    @property
    def ttl_s(self) -> int:
        return TTL_BUCKETS_S[self.ttl_idx]

    @property
    def placement_name(self) -> str:
        return PLACEMENTS[self.placement]

    @property
    def priority_name(self) -> str:
        return PRIORITY_LEVELS[self.priority]

    @property
    def writes_l1(self) -> bool:
        return self.placement in (PLACE_LOCAL, PLACE_BOTH)

    @property
    def writes_l2(self) -> bool:
        return self.placement in (PLACE_REDIS, PLACE_BOTH)


def _as_int(x, name: str, hi: int) -> int:
    if isinstance(x, (bool, np.bool_)):
        raise TypeError(f"{name} must be an integer, not bool")
    if not isinstance(x, (int, np.integer)):
        raise TypeError(f"{name} must be an integer, got {type(x).__name__}")
    x = int(x)
    if not 0 <= x < hi:
        raise ValueError(f"{name}={x} out of range [0, {hi})")
    return x


def encode_action(placement: int, ttl_idx: int, priority: int) -> int:
    p = _as_int(placement, "placement", N_PLACE)
    t = _as_int(ttl_idx, "ttl_idx", N_TTL)
    e = _as_int(priority, "priority", N_PRIO)
    return p * _STRIDE_P + t * _STRIDE_T + e


def decode_action(a: int) -> Action:
    a = _as_int(a, "action", N_ACTIONS)
    return Action(a // _STRIDE_P, (a // _STRIDE_T) % N_TTL, a % N_PRIO)


# Pre-decoded lookup tables for hot loops / vectorised analysis (index = flat action).
ACTION_TABLE: tuple[Action, ...] = tuple(decode_action(a) for a in range(N_ACTIONS))
PLACEMENT_OF = np.array([x.placement for x in ACTION_TABLE], dtype=np.int8)
TTL_IDX_OF = np.array([x.ttl_idx for x in ACTION_TABLE], dtype=np.int8)
PRIORITY_OF = np.array([x.priority for x in ACTION_TABLE], dtype=np.int8)
TTL_S_OF = np.array([TTL_BUCKETS_S[i] for i in TTL_IDX_OF], dtype=np.float64)


def actions_where(*, placement: int | None = None, ttl_idx: int | None = None,
                  priority: int | None = None) -> np.ndarray:
    """Flat action ids matching the given digit constraints (used by ablation arm C and the
    baseline ladder, e.g. 'fixed TTL, any priority, redis only')."""
    m = np.ones(N_ACTIONS, dtype=bool)
    if placement is not None:
        m &= PLACEMENT_OF == _as_int(placement, "placement", N_PLACE)
    if ttl_idx is not None:
        m &= TTL_IDX_OF == _as_int(ttl_idx, "ttl_idx", N_TTL)
    if priority is not None:
        m &= PRIORITY_OF == _as_int(priority, "priority", N_PRIO)
    return np.flatnonzero(m)


def nearest_ttl_idx(ttl_s: float) -> int:
    """Bucket whose log-distance to ``ttl_s`` is smallest (buckets are geometric, so compare in
    log space).  Used by baselines that compute a continuous TTL and must snap it to a bucket."""
    ttl_s = max(float(ttl_s), 1e-9)
    logs = np.log(np.asarray(TTL_BUCKETS_S, dtype=np.float64))
    return int(np.argmin(np.abs(logs - np.log(ttl_s))))
