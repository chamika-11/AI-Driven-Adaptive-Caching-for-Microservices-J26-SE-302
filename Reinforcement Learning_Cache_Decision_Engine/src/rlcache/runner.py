"""One place that wires simulator + feature tracker + reward + transition assembly together."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from .config import Config
from .features import FeatureTracker, Normalizer
from .predictor.standin import PredictorTables
from .sim.engine import Simulator, resolve_capacities
from .trace.record import Trace
from .transitions import Transition, TransitionAssembler


@dataclass
class Run:
    sim: Simulator
    asm: TransitionAssembler
    tracker: FeatureTracker

    def go(self, start: int = 0, end: int | None = None, measure_from: int | None = None):
        m = self.sim.run(start, end, measure_from)
        self.asm.finish()
        return m


def make_run(trace: Trace, cfg: Config, select: Callable[[np.ndarray, object], int], *,
             predictor: PredictorTables | None = None, normalizer: Normalizer | None = None,
             seed: int = 0, learn_normalizer: bool = False, emit=None, keep: bool = False,
             l1_capacity_bytes: int | None = None, l2_capacity_bytes: int | None = None,
             check_invariants: bool = False, keep_closed: bool = False,
             successor: str = "any") -> Run:
    l1, l2 = resolve_capacities(trace, cfg.cache)
    l1 = l1 if l1_capacity_bytes is None else int(l1_capacity_bytes)
    l2 = l2 if l2_capacity_bytes is None else int(l2_capacity_bytes)
    tracker = FeatureTracker(trace.n_keys, cfg.features, predictor, normalizer)
    asm = TransitionAssembler(tracker, cfg.reward, l1 + l2, select, emit=emit,
                              learn_normalizer=learn_normalizer, keep=keep, successor=successor)
    sim = Simulator(trace, cfg, asm, l1_capacity_bytes=l1, l2_capacity_bytes=l2, seed=seed,
                    observer=tracker, check_invariants=check_invariants, keep_closed=keep_closed,
                    record_latencies=False)
    return Run(sim, asm, tracker)
