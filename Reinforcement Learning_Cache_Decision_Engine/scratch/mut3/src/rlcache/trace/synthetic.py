"""Synthetic workload generator (R-D7, D-15, D-16).

Model
-----
* Reads: arrival times from an inhomogeneous (diurnal) Poisson process; keys drawn from a
  TRUNCATED Zipf(alpha) over ``n_keys`` ranks (numpy's ``zipf`` is unbounded and folding it with
  ``% n_keys`` distorts the tail -- C-11), then a temporal-locality redraw: with probability
  ``locality_prob`` the key is replaced by a uniform draw from the previous ``locality_window``
  requests' keys.
* Writes: an independent per-key Poisson mutation process with log-normally distributed rates,
  so volatility genuinely varies across keys.  Writes are source-of-truth mutations (A-1).
* Injectors: popularity permutation (with a retention knob), flash crowd, write-rate shift.
* The generator's hidden truth (``meta['true_write_rate']``) is for DIAGNOSTICS and oracle bounds
  only.  The predictor stand-in must be fitted from the trace's own early requests (D-16).

The trace spans hours (default 8 h) so that every TTL bucket up to 3600 s can expire (D-15).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from ..config import WorkloadConfig
from .record import OP_CODE, Trace

_TTL_LADDER = np.array([60, 300, 1800, 3600, 14400, 86400], dtype=np.int32)


@dataclass(frozen=True)
class PopularityShift:
    """Permute which keys are popular at ``at_frac`` of the duration.  ``retention`` is the
    fraction of keys whose rank is unchanged (1.0 = no change, 0.0 = full re-draw)."""
    at_frac: float
    retention: float = 0.0


@dataclass(frozen=True)
class FlashCrowd:
    """From ``at_frac`` for ``duration_frac`` of the trace, each read is redirected with
    probability ``boost`` to one of ``n_hot`` randomly chosen keys."""
    at_frac: float
    duration_frac: float
    n_hot: int = 10
    boost: float = 0.3


@dataclass(frozen=True)
class WriteRateShift:
    """Multiply every key's write rate by ``factor`` from ``at_frac`` of the duration on."""
    at_frac: float
    factor: float = 10.0


Shift = PopularityShift | FlashCrowd | WriteRateShift


def truncated_zipf_cdf(n_keys: int, alpha: float) -> np.ndarray:
    ranks = np.arange(1, n_keys + 1, dtype=np.float64)
    p = ranks ** (-alpha)
    c = np.cumsum(p)
    return c / c[-1]


def _diurnal_times(rng: np.random.Generator, n: int, T: float, amp: float, period: float):
    """n sorted arrival times on [0, T] with intensity 1 + amp*sin(2 pi t / period)."""
    grid = np.linspace(0.0, T, 4097)
    w = 2.0 * np.pi / period
    cdf = grid + amp * (1.0 - np.cos(w * grid)) / w
    cdf /= cdf[-1]
    u = np.sort(rng.random(n))
    return np.interp(u, cdf, grid)


def _gauss_rank(x: np.ndarray) -> np.ndarray:
    from scipy.special import ndtri
    r = np.argsort(np.argsort(x)).astype(np.float64)
    return ndtri((r + 0.5) / len(x))


def generate_synthetic(cfg: WorkloadConfig, shifts: Sequence[Shift] = (),
                       name: str | None = None) -> Trace:
    rng = np.random.default_rng(cfg.seed)
    n_keys, T = cfg.n_keys, float(cfg.duration_s)

    # popularity: rank -> key id permutation
    perm = rng.permutation(n_keys)
    pop_rank = np.empty(n_keys, dtype=np.int64)          # key id -> popularity rank (0 = hottest)
    pop_rank[perm] = np.arange(n_keys)

    # per-key write rate (lognormal), optional correlation with popularity
    lam = (1.0 / cfg.write_interval_median_s) * np.exp(
        cfg.write_rate_sigma * rng.standard_normal(n_keys))
    rho = float(np.clip(cfg.volatility_popularity_corr, 0.0, 1.0))
    if rho > 0.0:
        score = rho * _gauss_rank(-pop_rank.astype(np.float64)) \
            + np.sqrt(1 - rho * rho) * rng.standard_normal(n_keys)
        lam = np.sort(lam)[np.argsort(np.argsort(score))]

    # ---- writes (piecewise-constant rate multiplier) ---------------------------------------
    bounds = [0.0]
    mults = [1.0]
    for s in sorted((s for s in shifts if isinstance(s, WriteRateShift)), key=lambda s: s.at_frac):
        bounds.append(s.at_frac * T)
        mults.append(mults[-1] * s.factor)
    bounds.append(T)
    w_ts, w_key = [], []
    for (a, b), m in zip(zip(bounds[:-1], bounds[1:]), mults):
        counts = rng.poisson(lam * m * (b - a))
        tot = int(counts.sum())
        w_key.append(np.repeat(np.arange(n_keys), counts))
        w_ts.append(rng.uniform(a, b, tot))
    w_ts = np.concatenate(w_ts); w_key = np.concatenate(w_key)
    n_w = len(w_ts)
    n_r = cfg.n_requests - n_w
    if n_r < 0.2 * cfg.n_requests:
        raise ValueError(
            f"write volume {n_w} leaves only {n_r} reads of {cfg.n_requests}; raise "
            f"write_interval_median_s or n_requests")

    # ---- reads ------------------------------------------------------------------------------
    r_ts = _diurnal_times(rng, n_r, T, cfg.diurnal_amp, cfg.diurnal_period_s)
    cdf = truncated_zipf_cdf(n_keys, cfg.zipf_alpha)
    ranks = np.searchsorted(cdf, rng.random(n_r), side="right").clip(0, n_keys - 1)
    r_key = perm[ranks]
    for s in sorted((s for s in shifts if isinstance(s, PopularityShift)), key=lambda s: s.at_frac):
        new_perm = perm.copy()
        n_move = int(round((1.0 - s.retention) * n_keys))
        if n_move > 1:
            idx = rng.choice(n_keys, n_move, replace=False)
            new_perm[idx] = rng.permutation(new_perm[idx])
        late = r_ts >= s.at_frac * T
        r_key[late] = new_perm[ranks[late]]
        perm = new_perm
    # temporal locality: sequential so a redrawn key can itself be re-used later
    if cfg.locality_prob > 0:
        kk = r_key.tolist()
        u = rng.random(n_r); u2 = rng.random(n_r)
        L, p = cfg.locality_window, cfg.locality_prob
        for i in range(1, n_r):
            if u[i] < p:
                kk[i] = kk[i - 1 - int(u2[i] * min(L, i))]
        r_key = np.asarray(kk, dtype=np.int64)
    for s in (s for s in shifts if isinstance(s, FlashCrowd)):
        hot = rng.choice(n_keys, s.n_hot, replace=False)
        m = (r_ts >= s.at_frac * T) & (r_ts < (s.at_frac + s.duration_frac) * T)
        pick = m & (rng.random(n_r) < s.boost)
        r_key[pick] = hot[rng.integers(0, s.n_hot, int(pick.sum()))]

    # ---- merge, attributes ---------------------------------------------------------------------
    ts = np.concatenate([r_ts, w_ts])
    key = np.concatenate([r_key, w_key]).astype(np.int64)
    is_w = np.concatenate([np.zeros(n_r, bool), np.ones(n_w, bool)])
    order = np.argsort(ts, kind="stable")                # reads precede writes on exact ties
    ts, key, is_w = ts[order], key[order], is_w[order]

    sizes = np.clip(np.exp(cfg.size_lognorm_mu + cfg.size_lognorm_sigma * rng.standard_normal(n_keys)),
                    cfg.size_min, cfg.size_max).astype(np.int32)
    base_interval = 1.0 / lam
    key_ttl = _TTL_LADDER[np.argmin(
        np.abs(np.log(_TTL_LADDER[None, :]) - np.log(0.5 * base_interval)[:, None]), axis=1)]
    op = np.where(is_w, OP_CODE["set"], OP_CODE["get"]).astype(np.int8)
    ttl = np.where(is_w, key_ttl[key], 0).astype(np.int32)
    client = rng.integers(0, cfg.n_clients, len(ts)).astype(np.int32)

    tr = Trace(ts=ts, key=key, size=sizes[key], client=client, op=op, ttl=ttl, n_keys=n_keys,
               source="synthetic", name=name or f"synthetic_a{cfg.zipf_alpha}_s{cfg.seed}",
               meta={"true_write_rate": lam.copy(), "config": cfg, "shifts": tuple(shifts),
                     "generator": "synthetic_v1", "key_sample_frac": 1.0,
                     "n_reads": int(n_r), "n_writes": int(n_w)})
    tr.validate()
    return tr
