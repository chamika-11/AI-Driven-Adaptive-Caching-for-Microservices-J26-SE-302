"""Pending-transition assembly: (s, a, r, s') from closed insertions (M5; R-S5, R-S6, R-S9, D-9).

A decision at index ``i`` produces state ``s`` and action ``a``.  Its reward only exists when the
insertion CLOSES (last copy gone), possibly hours later.  The successor state ``s'`` is the
observation built at the NEXT decision point after closure (D-9).  Several insertions can close
between two decisions; all of them share that next observation.

* ``done`` is always False: the task is continuing (R-S5).  An insertion cut off by the end of
  the run (`truncated`) has no complete reward and is dropped, never stored as a terminal
  transition.
* Each transition carries ``dt = t_close - t_decision`` so a time-based discount ablation
  (D-11) is possible without changing the data.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

from .config import RewardWeights
from .features import FeatureTracker
from .features_spec import FEATURE_INDEX
from .reward import RewardParts, compute_reward
from .sim.engine import R_TRUNC, Insertion


@dataclass
class Transition:
    s: np.ndarray
    a: int
    r: float                  # clipped reward (what the learner sees)
    s2: np.ndarray
    done: bool                # always False
    dt: float                 # decision -> closure, seconds
    r_raw: float              # pre-clip value, for the D-10 clip-fraction log
    t_decision: float
    t_close: float
    idx: int                  # request index of the decision
    key: int
    reason: str
    parts: RewardParts


class TransitionAssembler:
    """A simulator policy that asks ``select(obs, ctx) -> action`` and emits transitions.

    Plug into :class:`~rlcache.sim.engine.Simulator` as ``policy`` AND ``observer=tracker``.
    """

    def __init__(self, tracker: FeatureTracker, weights: RewardWeights, cap_total_bytes: float,
                 select: Callable[[np.ndarray, object], int],
                 emit: Callable[[Transition], None] | None = None,
                 learn_normalizer: bool = False, keep: bool = False):
        self.tracker, self.w, self.cap = tracker, weights, float(cap_total_bytes)
        self.select, self.emit = select, emit
        self.learn_norm = learn_normalizer
        self.keep = keep
        self.kept: list[Transition] = []
        self._awaiting: list[tuple] = []         # (s, a, parts, ins): closed, awaiting s'
        self._cur: Optional[tuple] = None        # (obs, action) of the decision in flight
        self.n_decisions = 0
        self.n_emitted = 0
        self.n_dropped_truncated = 0
        self.n_dropped_tail = 0

    # ---- Simulator policy interface -----------------------------------------------------------
    def decide(self, ctx) -> int:
        obs = self.tracker.observe(ctx, update_norm=self.learn_norm)
        if self._awaiting:                       # D-9: s' = this decision's observation
            for (s, a, parts, ins) in self._awaiting:
                self._emit(s, a, parts, ins, obs)
            self._awaiting.clear()
        a = int(self.select(obs, ctx))
        self._cur = (obs, a)
        self.n_decisions += 1
        return a

    def on_decision(self, ins: Insertion) -> None:
        assert self._cur is not None
        ins.payload = self._cur
        self._cur = None

    def on_close(self, ins: Insertion) -> None:
        if ins.close_reason == R_TRUNC or ins.payload is None:
            self.n_dropped_truncated += 1
            return
        s, a = ins.payload
        # utilisation at decision time is feature #10, which the normaliser leaves unscaled
        parts = compute_reward(ins, self.w, self.cap, float(s[_UTIL]))
        self._awaiting.append((s, a, parts, ins))

    def finish(self) -> None:
        """End of run: closures with no later decision have no s' and are dropped."""
        self.n_dropped_tail += len(self._awaiting)
        self._awaiting.clear()

    # ---- internals ------------------------------------------------------------------------------
    def _emit(self, s, a, parts: RewardParts, ins: Insertion, s2) -> None:
        tr = Transition(s=s, a=a, r=parts.clipped, s2=s2, done=False,
                        dt=ins.close_time - ins.t_decision, r_raw=parts.raw,
                        t_decision=ins.t_decision, t_close=ins.close_time, idx=ins.idx,
                        key=ins.key, reason=ins.close_reason, parts=parts)
        self.n_emitted += 1
        if self.keep:
            self.kept.append(tr)
        if self.emit is not None:
            self.emit(tr)


_UTIL = FEATURE_INDEX["utilisation"]
