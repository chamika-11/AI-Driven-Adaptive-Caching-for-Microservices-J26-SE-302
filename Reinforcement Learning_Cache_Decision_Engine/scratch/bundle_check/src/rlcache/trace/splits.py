"""Chronological split (D-8, R-E1, R-P3).  Splits are by REQUEST INDEX and never shuffled.

    [0, f)   predictor fit   -- per-key write statistics are fitted here and then frozen
    [f, t)   agent training
    [t, v)   validation      -- all tuning, including baseline tuning
    [v, n)   test            -- touched once
"""
from __future__ import annotations

from dataclasses import dataclass

from ..config import SplitConfig
from .record import Trace


@dataclass(frozen=True)
class Splits:
    n: int
    fit_end: int
    train_end: int
    val_end: int

    @property
    def fit(self) -> tuple[int, int]:
        return 0, self.fit_end

    @property
    def train(self) -> tuple[int, int]:
        return self.fit_end, self.train_end

    @property
    def val(self) -> tuple[int, int]:
        return self.train_end, self.val_end

    @property
    def test(self) -> tuple[int, int]:
        return self.val_end, self.n

    def as_dict(self) -> dict[str, tuple[int, int]]:
        return {"fit": self.fit, "train": self.train, "val": self.val, "test": self.test}


def chronological_split(n: int, cfg: SplitConfig | None = None) -> Splits:
    cfg = cfg or SplitConfig()
    if n < 10:
        raise ValueError("trace too short to split")
    f, t, v = (int(n * x) for x in (cfg.predictor_fit_end, cfg.train_end, cfg.val_end))
    if not 0 < f < t < v < n:
        raise ValueError(f"degenerate split for n={n}: {(f, t, v)}")
    return Splits(n, f, t, v)


def split_traces(tr: Trace, cfg: SplitConfig | None = None) -> tuple[Splits, dict[str, Trace]]:
    sp = chronological_split(len(tr), cfg)
    return sp, {k: tr.slice(a, b) for k, (a, b) in sp.as_dict().items()}
