"""Workload-shift experiments (Addendum M11-E, E3): shift traces, time-resolved evaluation, the online-learning
variant and the pre-registered adaptation metrics.

Definitions (fixed in the addendum before any run): windows of W requests aligned to the test-slice start;
``h_w`` = hits / reads in window w; the shift sits at ``t_star`` (first request with ts >= at_frac * T).
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass

import numpy as np

from .config import N_ACTIONS, N_FEATURES, DQNConfig, WorkloadConfig
from .evaluation import EvalContext
from .runner import make_run
from .sim.engine import Simulator
from .trace.record import Trace
from .trace.synthetic import (DiurnalShift, FlashCrowd, PopularityShift, WriteRateShift,
                              generate_synthetic)

WINDOW = 5_000
AT_FRAC = 0.88
WRITE10_AT_FRAC = 0.914          # puts the x10 write shift at request index ~0.88 N (Amendment M11-E-b)
SHIFTS = ("perm", "flash", "diurnal", "write10")


def make_shift_trace(shift: str, seed: int, at_frac: float = AT_FRAC, n_requests: int = 600_000) -> Trace:
    cfg = WorkloadConfig(n_requests=n_requests, diurnal_amp=0.0, write_interval_median_s=28_800.0, seed=seed)
    spec = {
        "perm": PopularityShift(at_frac, retention=0.0),
        "flash": FlashCrowd(at_frac, 0.04, n_hot=10, boost=0.3),
        "diurnal": DiurnalShift(at_frac, amp=0.9, period_s=900.0),
        "write10": WriteRateShift(WRITE10_AT_FRAC, factor=10.0),
    }[shift]
    return generate_synthetic(cfg, (spec,), name=f"shift_{shift}_s{seed}")


def shift_index(trace: Trace, at_frac: float | None = None, duration_s: float | None = None) -> int:
    """First request at or after the shift (time fraction read from the trace's recorded shift)."""
    if at_frac is None:
        at_frac = float(trace.meta["shifts"][0].at_frac)
    T = duration_s if duration_s is not None else float(WorkloadConfig().duration_s)
    return int(np.searchsorted(trace.ts, at_frac * T, side="left"))


# ---- series recording ----------------------------------------------------------------------------
class SeriesRecorder:
    """Simulator observer: snapshots the cumulative read/hit/stale counters at the end of every window and
    forwards ``on_request`` to the policy's own observer (if any)."""

    def __init__(self, inner, start: int, window: int = WINDOW):
        self.inner, self.start, self.window = inner, start, window
        self.sim: Simulator | None = None
        self.snaps: list[tuple[int, int, int]] = []          # (reads, hits, stale) cumulative

    def on_request(self, i, t, k, is_write, hit) -> None:
        if self.inner is not None:
            self.inner.on_request(i, t, k, is_write, hit)
        if (i - self.start + 1) % self.window == 0 and self.sim is not None:
            m = self.sim.metrics
            self.snaps.append((m.n_reads, m.n_hit, m.n_stale))


def finish_series(sim: Simulator, rec: SeriesRecorder, a: int, b: int) -> dict:
    snaps = np.array([(0, 0, 0)] + rec.snaps, dtype=np.int64)
    d = np.diff(snaps, axis=0)
    reads, hits, stale = d[:, 0], d[:, 1], d[:, 2]
    n_w = len(reads)
    ttl = np.full(n_w, np.nan)
    by_w: dict[int, list[float]] = {}
    for ins in sim.closed:
        w = (ins.idx - a) // rec.window
        if 0 <= w < n_w:
            by_w.setdefault(w, []).append(ins.ttl_s)
    for w, v in by_w.items():
        ttl[w] = float(np.median(v))
    with np.errstate(invalid="ignore", divide="ignore"):
        return {"reads": reads.tolist(), "hit_ratio": (hits / reads).tolist(),
                "stale_rate": (stale / reads).tolist(), "ttl_median": ttl.tolist()}


def series_for_policy(ctx: EvalContext, policy, eviction: str = "sampled_lru", split: str = "test",
                      window: int = WINDOW) -> dict:
    """Run a (non-learning) policy over the slice and return its windowed series."""
    a, b, mf = ctx.slice_for(split)
    cfg = ctx.cfg
    if eviction != cfg.cache.base_eviction:
        cfg = dataclasses.replace(cfg, cache=dataclasses.replace(cfg.cache, base_eviction=eviction))
    rec = SeriesRecorder(policy if hasattr(policy, "on_request") else None, a, window)
    sim = Simulator(ctx.trace, cfg, policy, l1_capacity_bytes=ctx.l1_bytes, l2_capacity_bytes=ctx.l2_bytes,
                    seed=ctx.seed, keep_closed=True, record_latencies=False, observer=rec)
    rec.sim = sim
    sim.run(a, b, mf)
    return finish_series(sim, rec, a, b)


def series_online(ctx: EvalContext, res, cfg: DQNConfig | None = None, split: str = "test",
                  window: int = WINDOW, eps: float = 0.1, learning_starts: int = 2_000) -> dict:
    """ONLINE variant: continue learning on the slice with a fresh replay buffer (Addendum M11-E)."""
    from .agents.replay import ReplayBuffer
    cfg = cfg or DQNConfig()
    a, b, mf = ctx.slice_for(split)
    rng = np.random.default_rng([ctx.seed, 77])
    buf = ReplayBuffer(cfg.buffer_size, N_FEATURES, seed=ctx.seed + 7)
    learner, gamma = res.learner, res.gamma
    n = {"d": 0}

    def select(obs, c):
        n["d"] += 1
        act = int(rng.integers(0, N_ACTIONS)) if rng.random() < eps else int(np.argmax(learner.q_values(obs)))
        if n["d"] >= learning_starts and n["d"] % cfg.train_every == 0 and len(buf) >= cfg.batch_size:
            learner.train_step(buf.sample(cfg.batch_size), gamma)
            learner.soft_update(cfg.tau)
        return act

    kw = dict(predictor=ctx.predictor, l1_capacity_bytes=ctx.l1_bytes, l2_capacity_bytes=ctx.l2_bytes)
    run = make_run(ctx.trace, ctx.cfg, select, normalizer=res.norm, learn_normalizer=False,
                   emit=lambda tr: buf.add(tr.s, tr.a, tr.r, tr.s2, False), seed=ctx.seed, keep_closed=True, **kw)
    rec = SeriesRecorder(run.tracker, a, window)
    rec.sim = run.sim
    run.sim._observer = rec
    run.go(a, b, mf)
    return finish_series(run.sim, rec, a, b)


# ---- pre-registered metrics -----------------------------------------------------------------------
@dataclass
class ShiftMetrics:
    h_pre: float
    h_new: float
    dip_depth: float            # percentage points
    area_under_dip: float       # requests
    recovery_requests: float    # nan if censored
    censored: bool
    stale_spike: float
    ttl_before: float
    ttl_after: float


def _post_start(t_star: int, a: int, window: int) -> int:
    """First window lying entirely after the shift."""
    return -(-(t_star - a) // window)


def shift_metrics(series: dict, t_star: int, a: int, window: int = WINDOW) -> ShiftMetrics:
    h = np.asarray(series["hit_ratio"], float)
    s = np.asarray(series["stale_rate"], float)
    ttl = np.asarray(series["ttl_median"], float)
    j0 = _post_start(t_star, a, window)
    pre = slice(max(j0 - 7, 0), j0 - 1)                 # the six windows before the window containing t*
    post = np.arange(j0, len(h))
    h_pre = float(np.nanmean(h[pre]))
    h_new = float(np.nanmean(h[-4:]))
    dip = 100.0 * (h_pre - float(np.nanmin(h[post])))
    area = float(np.nansum(np.maximum(0.0, h_new - h[post])) * window)
    ok = h[post] >= 0.95 * h_new
    rec = float("nan")
    for k in range(len(post) - 2):
        if ok[k] and ok[k + 1] and ok[k + 2]:
            rec = float(k * window)
            break
    spike = float(np.nanmax(s[post]) - np.nanmean(s[pre]))
    return ShiftMetrics(h_pre, h_new, dip, area, rec, bool(np.isnan(rec)), spike,
                        float(np.nanmedian(ttl[pre])) if np.isfinite(ttl[pre]).any() else float("nan"),
                        float(np.nanmedian(ttl[post])) if np.isfinite(ttl[post]).any() else float("nan"))


def cumulative_regret(series: dict, ref_series: list[dict], t_star: int, a: int, window: int = WINDOW) -> float:
    """Sum over post-shift windows of max(0, best-baseline-in-hindsight hit ratio - this policy's hit ratio)."""
    h = np.asarray(series["hit_ratio"], float)
    ref = np.nanmax(np.vstack([np.asarray(r["hit_ratio"], float) for r in ref_series]), axis=0)
    j0 = _post_start(t_star, a, window)
    return float(np.nansum(np.maximum(0.0, ref[j0:] - h[j0:])))
