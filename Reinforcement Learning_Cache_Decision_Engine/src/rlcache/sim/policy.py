"""Trivial policies used by the simulator tests and as the first baselines (R-B1, R-B3)."""
from __future__ import annotations

import numpy as np

from ..actions import actions_where, encode_action
from ..config import N_ACTIONS


class FixedActionPolicy:
    """Always the same flat action."""

    def __init__(self, action: int):
        self.action = int(action)

    def decide(self, ctx) -> int:
        return self.action

    @classmethod
    def of(cls, placement: int, ttl_idx: int, priority: int = 1) -> "FixedActionPolicy":
        return cls(encode_action(placement, ttl_idx, priority))


class RandomPolicy:
    """Uniform over the 45 actions (R-B1 -- record its number)."""

    def __init__(self, seed: int = 0, actions: np.ndarray | None = None):
        self.rng = np.random.default_rng(seed)
        self.actions = np.arange(N_ACTIONS) if actions is None else np.asarray(actions)

    def decide(self, ctx) -> int:
        return int(self.actions[self.rng.integers(0, len(self.actions))])


class SequencePolicy:
    """Replays a scripted list of actions (hand-built tests)."""

    def __init__(self, actions: list[int]):
        self.actions = list(actions)
        self.i = 0

    def decide(self, ctx) -> int:
        a = self.actions[min(self.i, len(self.actions) - 1)]
        self.i += 1
        return a


__all__ = ["FixedActionPolicy", "RandomPolicy", "SequencePolicy", "actions_where"]
