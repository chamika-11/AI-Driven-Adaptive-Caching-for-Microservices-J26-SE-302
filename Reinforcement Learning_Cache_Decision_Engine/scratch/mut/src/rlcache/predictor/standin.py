"""Predictor stand-in (R-P1..R-P7): volatility, predicted TTL, hot-key flag, accuracy knob.

These formulas are THIS PROJECT'S OWN construction (A-9); no source defines a standard
"volatility score".  The stand-in is a test fixture and ablation instrument -- it does not replace
the teammates' LSTM/ARIMA component (C-32).

Leakage control (R-P3, R-P8)
----------------------------
:meth:`PredictorTables.fit` receives ONLY the predictor-fit slice ``trace[0:fit_end]``; nothing
after ``fit_end`` can influence any value.  Tables are then frozen (read-only arrays).  Keys never
seen in the fit slice get documented defaults, which is also how the agent behaves with the
predictor absent (R-P6).

``accuracy`` semantics (D-16, C-33)
-----------------------------------
accuracy=1.0 returns the FITTED tables (computed causally from the fit split -- not the
generator's hidden parameters).  accuracy=0.0 returns a permutation of the fitted values across
keys (same marginal, no information).  Two interpolation modes are provided:

* ``mixture`` (default): element-wise keep the true value with probability ``accuracy``, else take
  the value of a random other key.  The marginal distribution is preserved EXACTLY at every
  accuracy level, so "worse prediction" is not confounded with "different input scale".
* ``interpolate`` (the MD's literal version): ``a*true + (1-a)*shuffled``.  This shrinks the
  variance by ``a^2 + (1-a)^2`` at intermediate ``a`` -- contradicting the MD's claim that the
  marginal is identical (C-33).  Kept for completeness and tested to demonstrate the shrinkage.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np

from ..trace.record import Trace

TTL_FLOOR_S = 1.0
TTL_CEIL_S = 3600.0
VOL_HALF_LIFE_S = 300.0         # squash scale of the write-rate term (MD)
TTL_QUANTILE = 0.20
HOT_TOP_FRACTION = 0.01         # A-11

# Predictor-absent defaults (R-P6); mirror the MD's GroupPrediction() contract defaults.
ABSENT_VOLATILITY = 0.5
ABSENT_TTL_S = 60.0             # log-midpoint of [1, 3600]
ABSENT_HOT = 0.0


# ---- group statistics helpers -----------------------------------------------------------------
def _inter_write_gaps(tr: Trace) -> tuple[np.ndarray, np.ndarray]:
    """(key_of_gap, gap_seconds) for consecutive writes of the same key within ``tr``."""
    w = tr.is_write
    wk, wt = tr.key[w], tr.ts[w]
    if len(wk) < 2:
        return np.empty(0, np.int64), np.empty(0, np.float64)
    order = np.lexsort((wt, wk))                          # by key, then time
    wk, wt = wk[order], wt[order]
    same = wk[1:] == wk[:-1]
    return wk[1:][same], (wt[1:] - wt[:-1])[same]


def _group_quantile(gap_keys: np.ndarray, gaps: np.ndarray, n_keys: int, q: float) -> np.ndarray:
    """Per-key quantile with numpy's default linear interpolation; NaN where no gaps."""
    out = np.full(n_keys, np.nan)
    if gaps.size == 0:
        return out
    order = np.lexsort((gaps, gap_keys))
    gk, g = gap_keys[order], gaps[order]
    uniq, start, cnt = np.unique(gk, return_index=True, return_counts=True)
    pos = q * (cnt - 1)
    lo = np.floor(pos).astype(np.int64)
    hi = np.minimum(lo + 1, cnt - 1)
    frac = pos - lo
    out[uniq] = g[start + lo] * (1 - frac) + g[start + hi] * frac
    return out


@dataclass(frozen=True)
class GapStats:
    """Per-key inter-write gap statistics from a fit slice (statistics-TTL baselines, R-B3)."""
    mean: np.ndarray
    median: np.ndarray
    p10: np.ndarray
    n_gaps: np.ndarray


def fit_gap_stats(tr: Trace) -> GapStats:
    gk, g = _inter_write_gaps(tr)
    n = tr.n_keys
    cnt = np.bincount(gk, minlength=n)
    mean = np.full(n, np.nan)
    nz = cnt > 0
    mean[nz] = np.bincount(gk, weights=g, minlength=n)[nz] / cnt[nz]
    return GapStats(mean, _group_quantile(gk, g, n, 0.5), _group_quantile(gk, g, n, 0.1), cnt)


def compute_volatility(tr: Trace, half_life: float = VOL_HALF_LIFE_S) -> np.ndarray:
    """0.5 * squashed write rate + 0.3 * write ratio + 0.2 * CV of inter-write gaps, in [0, 1]."""
    n = tr.n_keys
    W = max(tr.duration_s, 1.0)
    writes = np.bincount(tr.key[tr.is_write], minlength=n).astype(np.float64)
    access = np.bincount(tr.key, minlength=n).astype(np.float64)
    f_norm = 1.0 - np.exp(-(writes / W) * half_life)
    r = writes / np.maximum(access, 1.0)
    gk, g = _inter_write_gaps(tr)
    cv = np.zeros(n)
    cnt = np.bincount(gk, minlength=n)
    ok = cnt >= 2                                          # >= 3 writes -> >= 2 gaps
    if ok.any():
        s1 = np.bincount(gk, weights=g, minlength=n)
        s2 = np.bincount(gk, weights=g * g, minlength=n)
        mean = np.where(cnt > 0, s1 / np.maximum(cnt, 1), 0.0)
        var = np.maximum(s2 / np.maximum(cnt, 1) - mean * mean, 0.0)    # population std
        cv[ok] = np.sqrt(var[ok]) / np.maximum(mean[ok], 1e-9)
    cv = np.clip(cv, 0.0, 2.0) / 2.0
    return np.clip(0.5 * f_norm + 0.3 * r + 0.2 * cv, 0.0, 1.0).astype(np.float32)


def compute_predicted_ttl(tr: Trace, quantile: float = TTL_QUANTILE,
                          floor: float = TTL_FLOOR_S, ceil: float = TTL_CEIL_S) -> np.ndarray:
    """20th percentile of inter-write gaps clipped to [1, 3600]; never-gapped keys -> ceil."""
    gk, g = _inter_write_gaps(tr)
    q = _group_quantile(gk, g, tr.n_keys, quantile)
    out = np.where(np.isnan(q), ceil, np.clip(q, floor, ceil))
    return out.astype(np.float32)


def compute_hot_flag(tr: Trace, top_fraction: float = HOT_TOP_FRACTION) -> np.ndarray:
    """A-11: keys in the top ``top_fraction`` of request counts among keys seen in the slice.

    Ties at the cut-off are EXCLUDED (a key is hot only if its count is strictly greater than the
    (k+1)-th largest), so at most ``k = ceil(top_fraction * n_seen)`` keys are flagged and no
    arbitrary tie-break is needed.  A key must also have been requested at least twice.
    """
    cnt = np.bincount(tr.key, minlength=tr.n_keys)
    seen = cnt[cnt > 0]
    out = np.zeros(tr.n_keys, dtype=np.float32)
    if seen.size == 0:
        return out
    k = max(int(np.ceil(top_fraction * seen.size)), 1)
    if k >= seen.size:
        return out                                        # everything would be "hot": no signal
    thr = max(np.partition(seen, -(k + 1))[-(k + 1)], 1)  # (k+1)-th largest count
    out[cnt > thr] = 1.0
    out[cnt < 2] = 0.0
    return out


def _freeze(a: np.ndarray) -> np.ndarray:
    a = np.array(a, dtype=np.float32, copy=True)
    a.setflags(write=False)
    return a


@dataclass(frozen=True)
class PredictorTables:
    volatility: np.ndarray
    predicted_ttl: np.ndarray
    hot_key: np.ndarray
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def n_keys(self) -> int:
        return len(self.volatility)

    def lookup(self, key: int) -> tuple[float, float, float]:
        return (float(self.volatility[key]), float(self.predicted_ttl[key]),
                float(self.hot_key[key]))

    # ---- constructors -----------------------------------------------------------------------
    @classmethod
    def fit(cls, tr: Trace, fit_end: int) -> "PredictorTables":
        """Fit on ``tr[0:fit_end]`` only (R-P3).  The returned arrays are read-only."""
        if not 0 < fit_end <= len(tr):
            raise ValueError("fit_end out of range")
        sl = tr.slice(0, fit_end)
        return cls(_freeze(compute_volatility(sl)), _freeze(compute_predicted_ttl(sl)),
                   _freeze(compute_hot_flag(sl)),
                   {"source": "fitted", "fit_end": int(fit_end), "uses_future": False,
                    "accuracy": 1.0, "fit_t_end": float(sl.ts[-1])})

    @classmethod
    def absent(cls, n_keys: int) -> "PredictorTables":
        """Predictor unavailable (R-P6): constant defaults -> carries no per-key information."""
        return cls(_freeze(np.full(n_keys, ABSENT_VOLATILITY)),
                   _freeze(np.full(n_keys, ABSENT_TTL_S)),
                   _freeze(np.full(n_keys, ABSENT_HOT)),
                   {"source": "absent", "uses_future": False, "accuracy": 0.0})

    @classmethod
    def oracle_bound(cls, tr: Trace) -> "PredictorTables":
        """BOUND, not a baseline: statistics from the WHOLE trace (uses future information)."""
        return cls(_freeze(compute_volatility(tr)), _freeze(compute_predicted_ttl(tr)),
                   _freeze(compute_hot_flag(tr)),
                   {"source": "oracle_bound", "uses_future": True, "accuracy": 1.0})

    # ---- accuracy knob (R-P4) ---------------------------------------------------------------
    def with_accuracy(self, accuracy: float, rng: np.random.Generator,
                      mode: str = "mixture") -> "PredictorTables":
        a = float(np.clip(accuracy, 0.0, 1.0))
        if mode not in ("mixture", "interpolate"):
            raise ValueError("mode must be 'mixture' or 'interpolate'")
        n = self.n_keys
        perm = rng.permutation(n)                         # one shared permutation for all fields
        keep = rng.random(n) < a                          # shared mask: fields stay consistent
        out = []
        for arr, lo, hi in ((self.volatility, 0.0, 1.0),
                            (self.predicted_ttl, TTL_FLOOR_S, TTL_CEIL_S),
                            (self.hot_key, 0.0, 1.0)):
            shuffled = arr[perm]
            if mode == "mixture":
                v = np.where(keep, arr, shuffled)
            else:
                v = a * arr + (1.0 - a) * shuffled
            out.append(_freeze(np.clip(v, lo, hi)))
        meta = dict(self.meta, accuracy=a * float(self.meta.get("accuracy", 1.0)),
                    accuracy_mode=mode)
        return replace(self, volatility=out[0], predicted_ttl=out[1], hot_key=out[2], meta=meta)


def synthetic_predictor(true_values: np.ndarray, accuracy: float, rng: np.random.Generator,
                        kind: str = "ttl", mode: str = "mixture") -> np.ndarray:
    """Single-array form of the accuracy knob (MD signature, plus ``mode``)."""
    a = float(np.clip(accuracy, 0.0, 1.0))
    shuffled = rng.permutation(true_values)
    if mode == "mixture":
        out = np.where(rng.random(len(true_values)) < a, true_values, shuffled)
    elif mode == "interpolate":
        out = a * true_values + (1.0 - a) * shuffled
    else:
        raise ValueError(mode)
    lo = TTL_FLOOR_S if kind == "ttl" else 0.0
    hi = TTL_CEIL_S if kind == "ttl" else 1.0
    return np.clip(out, lo, hi).astype(np.float32)
