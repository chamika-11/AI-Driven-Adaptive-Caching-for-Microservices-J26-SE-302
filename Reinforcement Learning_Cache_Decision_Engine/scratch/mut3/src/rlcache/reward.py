"""Multi-objective reward of one closed insertion (M5; R-R1..R-R5, D-10, D-11).

    r = u * [ w_hit * H + w_lat * sum(exp(-L/L0)) - w_stale * sum(min(1, age/ttl))
              - w_backend * F / F_ref - w_mem * byte_s / (cap * T) ]  -  w_stampede * max(0, c-1) / 2.4

* Read-level terms are SUMMED over the reads this decision served (D-10); ``H`` = hits served by
  the insertion's copies, the creating miss is excluded (its latency was fixed before the action).
* ``F`` = backend fetches in the insertion's window (the creating fetch plus overlapping
  duplicate fetches, ``ins.concurrent``); ``F_ref`` = the no-cache baseline for the same window,
  where every read is a fetch: ``concurrent + H`` (R-R4).
* ``u`` is the utilisation gate evaluated at DECISION time (the state the agent chose in).
* The stampede term sits outside the gate (R-R3).
* The learner-facing reward is ``clip(raw / scale, -clip, clip)`` (R-R5, D-32); ``raw`` (after
  weighting, gate and stampede, before scaling) is returned so the clip fraction can be logged
  (D-10 requires it).
* These terms are part of the true objective, not "reward shaping" in the Ng-Harada-Russell
  sense (R-R7): they are meant to change the optimum.
"""
from __future__ import annotations

from dataclasses import dataclass

from .config import RewardWeights
from .sim.engine import Insertion


@dataclass(frozen=True)
class RewardParts:
    hit: float
    lat: float
    stale: float
    backend: float
    mem: float
    stampede: float
    gate: float
    raw: float        # after gate and stampede, before scaling/clipping
    clipped: float    # clip(raw / scale, +-clip): what the learner is trained on


def utilisation_gate(util: float, start: float = 0.9) -> float:
    return 1.0 - max(0.0, util - start) / max(1.0 - start, 1e-12) if util > start else 1.0


def compute_reward(ins: Insertion, w: RewardWeights, cap_total_bytes: float,
                   util_at_decision: float) -> RewardParts:
    gate = max(0.0, utilisation_gate(util_at_decision, w.util_gate_start)) if w.gate_enabled else 1.0
    H = ins.hits
    hit = w.w_hit * H
    lat = w.w_lat * ins.lat_score_sum
    stale = w.w_stale * ins.stale_cost_sum
    c = ins.concurrent
    backend = w.w_backend * (c / (c + H))
    mem = w.w_mem * ins.byte_seconds / (cap_total_bytes * w.mem_window_s)
    stamp = w.w_stampede * max(0, c - 1) / w.stampede_norm
    raw = gate * (hit + lat - stale - backend - mem) - stamp
    clipped = max(-w.clip, min(w.clip, raw / w.scale))
    return RewardParts(hit, lat, stale, backend, mem, stamp, gate, raw, clipped)
