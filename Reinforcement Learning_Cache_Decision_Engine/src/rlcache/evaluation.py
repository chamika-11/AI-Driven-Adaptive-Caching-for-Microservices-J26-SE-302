"""Evaluation runner (M6): chronological splits, warm-up exclusion, results.csv rows.

Protocol (docs/PREREGISTRATION.md, M6-2):
* statistics / predictor fit on request indices [0, 30%) only;
* validation [70%, 80%), test [80%, 100%];
* every run starts with a COLD cache at the slice start and excludes the first ``WARMUP_FRAC`` of
  the slice from the metrics (the state still evolves during warm-up);
* equal total capacity for every policy: the same L1 and L2 byte sizes;
* the scalar ``utility`` is for within-family selection on validation only.
"""
from __future__ import annotations

import dataclasses
import math
import time
from dataclasses import dataclass, field

import numpy as np

from .actions import PLACEMENT_OF
from .baselines.bounds import _next_read_index, belady_bound
from .baselines.policies import Spec
from .config import (N_ACTIONS, STALENESS_PRESETS, Config, WorkloadConfig)
from .predictor.standin import GapStats, PredictorTables, fit_gap_stats
from .sim.engine import Simulator, resolve_capacities
from .trace.oracle import Oracle, annotate_oracle
from .trace.record import Trace
from .trace.splits import Splits, chronological_split
from .trace.synthetic import generate_synthetic

WARMUP_FRAC = 0.10
W_HIT, W_LAT, W_STALE = 1.0, 0.5, 3.0          # the U weights (spec reward ingredients)


@dataclass
class EvalContext:
    seed: int
    arm: str
    capacity_frac: float
    trace: Trace
    splits: Splits
    cfg: Config
    predictor: PredictorTables
    gap_stats: GapStats
    oracle: Oracle
    l1_bytes: int
    l2_bytes: int
    trace_name: str
    _next_read: np.ndarray | None = field(default=None, repr=False)

    @property
    def next_read(self) -> np.ndarray:
        if self._next_read is None:
            self._next_read = _next_read_index(self.trace)
        return self._next_read

    @classmethod
    def build(cls, seed: int, capacity_frac: float, arm: str = "harsh",
              workload: WorkloadConfig | None = None, trace: Trace | None = None,
              w_stale: float | None = None, base_eviction: str | None = None) -> "EvalContext":
        wl = workload or WorkloadConfig()
        if trace is None:
            trace = generate_synthetic(dataclasses.replace(wl, seed=seed))
        sp = chronological_split(len(trace))
        base = Config()
        cfg = dataclasses.replace(
            base, staleness=STALENESS_PRESETS[arm],
            cache=dataclasses.replace(base.cache, l2_footprint_frac=capacity_frac))
        if base_eviction is not None:                   # Addendum M11-F: the agent's own simulator eviction
            cfg = dataclasses.replace(cfg, cache=dataclasses.replace(cfg.cache, base_eviction=base_eviction))
        if w_stale is not None:                         # Addendum M11-E (E2): reward weight only
            cfg = dataclasses.replace(cfg, reward=dataclasses.replace(cfg.reward, w_stale=float(w_stale)))
        l1, l2 = resolve_capacities(trace, cfg.cache)
        return cls(seed=seed, arm=arm, capacity_frac=capacity_frac, trace=trace, splits=sp,
                   cfg=cfg, predictor=PredictorTables.fit(trace, sp.fit_end),
                   gap_stats=fit_gap_stats(trace.slice(0, sp.fit_end)),
                   oracle=annotate_oracle(trace), l1_bytes=l1, l2_bytes=l2,
                   trace_name=trace.name)

    def slice_for(self, split: str) -> tuple[int, int, int]:
        a, b = {"val": self.splits.val, "test": self.splits.test}[split]
        return a, b, a + int(WARMUP_FRAC * (b - a))

    def capacity_objects(self) -> int:
        n_unique = max(self.trace.n_unique_keys(), 1)
        mean_size = self.trace.footprint_bytes() / n_unique
        return max(1, int((self.l1_bytes + self.l2_bytes) / mean_size))


def _pct(x: np.ndarray, q: float) -> float:
    return float(np.percentile(x, q)) if len(x) else float("nan")


def _base_row(ctx: EvalContext, spec: Spec, split: str) -> dict:
    return {
        "run_id": ("" if ctx.trace.source == "synthetic" else f"{ctx.trace_name}|")
        + f"{spec.family}|{spec.name}|{ctx.arm}|cap{ctx.capacity_frac}|{split}|s{ctx.seed}",
        "config_digest": ctx.cfg.digest(), "git_commit": "nogit", "seed": ctx.seed,
        "data_source": ctx.trace.source if ctx.trace.source in ("synthetic", "twitter_real") else "synthetic",
        "trace_name": ctx.trace_name, "split": split,
        "policy": spec.name, "policy_class": spec.policy_class, "family": spec.family,
        "capacity_frac": ctx.capacity_frac, "l1_frac": ctx.cfg.cache.l1_fraction_of_l2,
        "staleness_mode": ctx.arm, "w_stale": ctx.cfg.reward.w_stale, "predictor_accuracy": 1.0,
        "notes": ("post-hoc: added after a dev-seed diagnostic, before evaluation seeds ran "
                  "(PREREGISTRATION M6-B)") if spec.post_hoc else (
                      f"base_eviction={spec.eviction} (Addendum M11-E)" if spec.eviction != "sampled_lru" else ""),
    }


def evaluate_sim_policy(ctx: EvalContext, spec: Spec, split: str, policy=None) -> dict:
    """Run one policy on one split.  ``policy`` lets a caller keep a handle on the object (e.g. to
    read diagnostics afterwards); by default it is built from ``spec.make(ctx)``."""
    a, b, mf = ctx.slice_for(split)
    policy = policy if policy is not None else spec.make(ctx)
    cfg = ctx.cfg
    if spec.eviction != cfg.cache.base_eviction:
        cfg = dataclasses.replace(cfg, cache=dataclasses.replace(cfg.cache, base_eviction=spec.eviction))
    sim = Simulator(ctx.trace, cfg, policy, l1_capacity_bytes=ctx.l1_bytes,
                    l2_capacity_bytes=ctx.l2_bytes, seed=ctx.seed, keep_closed=True,
                    record_latencies=True,
                    observer=policy if hasattr(policy, "on_request") else None)
    t0 = time.perf_counter()
    m = sim.run(a, b, mf)
    wall = time.perf_counter() - t0
    row = _base_row(ctx, spec, split)
    n = m.n_reads
    lat = np.asarray(sim.latencies, float) * 1e6 if sim.latencies else np.empty(0)
    ages = np.asarray(m.stale_ages, float)
    # decision behaviour over measured decisions
    meas = [i for i in sim.closed if i.measured]
    ttl = np.array([i.ttl_s for i in meas], float)
    acts = np.array([i.action for i in meas], int)
    if len(meas):
        tnw = ctx.oracle.next_write_ts[[i.idx for i in meas]] - np.array([i.t_decision for i in meas])
        cap = float(max(ctx.cfg.cache.hard_cap_s, 1))
        target = np.minimum(tnw, 3600.0)
        over = float(np.mean(ttl > tnw))
        mae = float(np.mean(np.abs(ttl - target)))
        hist = np.bincount(acts, minlength=N_ACTIONS).astype(float)
        p = hist / hist.sum()
        ent = float(-(p[p > 0] * np.log(p[p > 0])).sum() / math.log(N_ACTIONS))
        pl = np.bincount(PLACEMENT_OF[acts], minlength=3) / len(acts)
    else:
        over = mae = ent = float("nan")
        pl = np.array([float("nan")] * 3)
    util = (W_HIT * m.n_hit + W_LAT * (m.lat_score_hits + m.lat_score_miss)
            - W_STALE * m.stale_cost) / n if n else float("nan")
    row.update({
        "n_reads": n, "n_fresh": m.n_fresh, "n_stale": m.n_stale, "n_miss": m.n_miss,
        "n_writes": m.n_writes, "n_decisions": m.n_decisions,
        "ohr": m.ohr(), "bhr": m.bytes_hit / m.bytes_read if m.bytes_read else float("nan"),
        "stale_read_rate": m.stale_read_rate(),
        "stale_given_hit": m.n_stale / m.n_hit if m.n_hit else float("nan"),
        "stale_age_mean_s": float(ages.mean()) if len(ages) else 0.0,
        "stale_age_p95_s": _pct(ages, 95) if len(ages) else 0.0,
        "backend_per_1k_reads": 1000.0 * m.backend_fetches / n if n else float("nan"),
        "lat_mean_us": float(lat.mean()) if len(lat) else float("nan"),
        "lat_p50_us": _pct(lat, 50), "lat_p95_us": _pct(lat, 95), "lat_p99_us": _pct(lat, 99),
        "lat_p999_us": _pct(lat, 99.9),
        "cap_evictions_per_1k": 1000.0 * m.cap_evictions / n if n else float("nan"),
        "ttl_expirations_per_1k": 1000.0 * m.ttl_expirations / n if n else float("nan"),
        "ttl_median_s": float(np.median(ttl)) if len(ttl) else float("nan"),
        "over_ttl_frac": over, "ttl_mae_s": mae,
        "share_local": float(pl[0]), "share_redis": float(pl[1]), "share_both": float(pl[2]),
        "action_entropy_norm": ent, "utility": util,
        "throughput_req_per_s": (b - a) / max(wall, 1e-9),
    })
    return row


def evaluate_belady(ctx: EvalContext, spec: Spec, split: str) -> dict:
    a, b, mf = ctx.slice_for(split)
    res = belady_bound(ctx.trace, ctx.oracle, ctx.capacity_objects(), a, b, mf,
                       ttl_constrained=(spec.name == "belady_ttl_constrained"),
                       next_read=ctx.next_read)
    row = _base_row(ctx, spec, split)
    n, h, s = res["reads"], res["hits"], res["stale"]
    row.update({"n_reads": n, "n_fresh": h - s, "n_stale": s, "n_miss": n - h,
                "ohr": res["ohr"], "stale_read_rate": res["stale_rate"],
                "stale_given_hit": s / h if h else 0.0,
                "notes": f"unit-size object bound; capacity_objects={ctx.capacity_objects()}"})
    return row


def evaluate(ctx: EvalContext, spec: Spec, split: str) -> dict:
    if spec.family == "belady":
        return evaluate_belady(ctx, spec, split)
    return evaluate_sim_policy(ctx, spec, split)
