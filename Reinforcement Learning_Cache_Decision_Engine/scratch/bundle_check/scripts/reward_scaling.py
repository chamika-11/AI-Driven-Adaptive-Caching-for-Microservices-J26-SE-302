"""D-10 reward-scaling study.  Criterion is declared in docs/REWARD_SCALING.md (read it first).

    python scripts/reward_scaling.py            # dev seeds 100-102, capacities 5% and 25%

Synthetic data, development seeds only.
"""
from __future__ import annotations

import dataclasses
import json
import math
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
sys.path.insert(0, str(HERE))
import placement_signal as ps  # noqa: E402
from rlcache.actions import decode_action, encode_action  # noqa: E402
from rlcache.config import Config  # noqa: E402
from rlcache.features_spec import FEATURE_INDEX  # noqa: E402
from rlcache.reward import compute_reward  # noqa: E402
from rlcache.runner import make_run  # noqa: E402
from rlcache.sim.engine import R_TRUNC  # noqa: E402
from rlcache.sim.policy import RandomPolicy  # noqa: E402

UTIL = FEATURE_INDEX["utilisation"]
DEV_SEEDS = (100, 101, 102)
CAPS = (0.05, 0.25)
MIN_CELL = 20

TRANSFORMS = {
    "clip10": lambda r, h: np.clip(r, -10, 10),
    "raw": lambda r, h: r,
    "div10_clip": lambda r, h: np.clip(r / 10.0, -10, 10),
    "div100_clip": lambda r, h: np.clip(r / 100.0, -10, 10),
    "symlog": lambda r, h: np.sign(r) * np.log1p(np.abs(r)),
    "per_read": lambda r, h: r / (1.0 + h),
}
# Addendum A (post-hoc): the same transforms on the reward without the utilisation gate
for _b in ("clip10", "raw", "div100_clip", "symlog"):
    TRANSFORMS[_b + "_ng"] = TRANSFORMS[_b]


def regime(frac: float) -> ps.Regime:
    # harsh staleness is the Config() default; Regime fields mirror it explicitly
    return ps.Regime(f"harsh_cap{frac}", frac=frac, ratio=0.10, p_inv=0.2, d_inv=10.0, p_bypass=0.3)


def _cfg(r: ps.Regime) -> Config:
    return ps.make_cfg(r)


def _decision_data(seed: int, r: ps.Regime, action: int | None, a: int, b: int, rand_seed=None):
    """Run [a, b); return per-decision arrays for non-truncated closures."""
    tr = ps.get_trace(seed, r.alpha, r.n_requests, r.n_keys)
    cfg = _cfg(r)
    if action is None:
        pol = RandomPolicy(rand_seed or 0)
        select = lambda obs, ctx: pol.decide(ctx)           # noqa: E731
    else:
        select = lambda obs, ctx: action                    # noqa: E731
    run = make_run(tr, cfg, select, keep_closed=True, seed=0)
    run.go(a, b, a)
    cap = run.sim.l1.cap + run.sim.l2.cap
    key, raw, clipped, hits, idx, raw_ng = [], [], [], [], [], []
    for ins in run.sim.closed:
        if ins.close_reason == R_TRUNC or ins.payload is None:
            continue
        p = compute_reward(ins, cfg.reward, cap, float(ins.payload[0][UTIL]))
        key.append(ins.key); raw.append(p.raw); clipped.append(p.clipped)
        raw_ng.append(p.hit + p.lat - p.stale - p.backend - p.mem - p.stampede)   # gate removed
        hits.append(ins.hits); idx.append(ins.idx)
    return {"key": np.array(key), "raw": np.array(raw), "raw_ng": np.array(raw_ng),
            "clipped": np.array(clipped),
            "hits": np.array(hits), "idx": np.array(idx), "n_created": run.sim.n_created}


def _hist_job(args):
    seed, frac, label, action = args
    r = regime(frac)
    d = _decision_data(seed, r, action, 0, r.n_requests, rand_seed=seed)
    return label, seed, frac, d["raw"], d["hits"]


def _train_job(args):
    seed, frac, action, mid = args
    r = regime(frac)
    d = _decision_data(seed, r, action, 0, mid)
    return action, d


def _eval_job(args):
    seed, frac, cls, act_of_class, mid, n, label = args
    r = regime(frac)
    o = ps.agg_run(seed, r, ps.ClassPolicy(cls, act_of_class), mid, n)
    return label, o["U"], o["ohr"], o["stale_rate"]


def run_cell(seed: int, frac: float, pool: Pool) -> dict:
    r = regime(frac)
    tr = ps.get_trace(seed, r.alpha, r.n_requests, r.n_keys)
    n = len(tr)
    mid = n // 2
    cls, _ = ps.build_classes(tr, mid)
    NC = 10
    train = dict(pool.map(_train_job, [(seed, frac, a, mid) for a in ps.ACTS], chunksize=1))
    ug = pool.map(ps._train_job, [(seed, r, a, 0, mid) for a in ps.ACTS], chunksize=1)
    u_cls = {a: np.bincount(cls, weights=u, minlength=NC) for a, u, *_ in ug}
    tot = {a: float(u.sum()) for a, u, *_ in ug}
    a_star = max(ps.ACTS, key=lambda a: tot[a])

    def choose(score):                      # score(a, c) -> value or None if cell too small
        out = np.full(NC, a_star, dtype=np.int64)
        for c in range(NC - 1):
            best, best_v = None, -np.inf
            for a in ps.ACTS:
                v = score(a, c)
                if v is not None and v > best_v:
                    best, best_v = a, v
            if best is not None:
                out[c] = best
        return out

    policies = {"fixed_best": np.full(NC, a_star, dtype=np.int64),
                "U_optimal_class": choose(lambda a, c: u_cls[a][c])}
    for name, f in TRANSFORMS.items():
        cache = {}
        for a in ps.ACTS:
            d = train[a]
            c_of = cls[d["key"]]
            v = f(d["raw_ng"] if name.endswith("_ng") else d["raw"], d["hits"])
            for c in range(NC - 1):
                m = c_of == c
                cache[(a, c)] = (float(v[m].mean()) if m.sum() >= MIN_CELL else None,
                                 float(v[m].sum()) if m.sum() >= MIN_CELL else None)
        policies[f"{name}|mean"] = choose(lambda a, c, k=cache: k[(a, c)][0])
        policies[f"{name}|sum"] = choose(lambda a, c, k=cache: k[(a, c)][1])
    ev = pool.map(_eval_job, [(seed, frac, cls, act, mid, n, lab) for lab, act in policies.items()],
                  chunksize=1)
    return {lab: (U, ohr, st) for lab, U, ohr, st in ev}


def main():
    t0 = time.time()
    out = {}
    with Pool(10) as pool:
        # ---- clip-fraction table ----------------------------------------------------------
        jobs = [(s, f, lab, act) for s in DEV_SEEDS for f in CAPS
                for lab, act in (("random45", None), ("redis/3600", encode_action(1, 4, 1)),
                                 ("redis/30", encode_action(1, 1, 1)))]
        res = pool.map(_hist_job, jobs, chunksize=1)
        print("## pre-clip reward distribution (full dev traces, D-10 literal sum aggregation)")
        print(f"{'policy':<12}{'cap':>6}{'decisions':>11}{'clip>10 %':>11}{'p50':>8}{'p90':>8}"
              f"{'p99':>9}{'max':>10}{'H=0 %':>8}{'mean H':>9}")
        hist = {}
        for lab in ("random45", "redis/3600", "redis/30"):
            for f in CAPS:
                raws = np.concatenate([x[3] for x in res if x[0] == lab and x[2] == f])
                hs = np.concatenate([x[4] for x in res if x[0] == lab and x[2] == f])
                clipfrac = float(np.mean(np.abs(raws) > 10)) * 100
                print(f"{lab:<12}{f:6.2f}{len(raws):11d}{clipfrac:11.2f}{np.percentile(raws,50):8.2f}"
                      f"{np.percentile(raws,90):8.2f}{np.percentile(raws,99):9.2f}{raws.max():10.1f}"
                      f"{100*np.mean(hs==0):8.1f}{hs.mean():9.2f}")
                hist[f"{lab}@{f}"] = {"clip_pct": clipfrac, "n": int(len(raws)),
                                      "p50": float(np.percentile(raws, 50)),
                                      "p99": float(np.percentile(raws, 99)), "max": float(raws.max())}
        out["clip"] = hist
        # ---- alignment study --------------------------------------------------------------
        cells = {}
        for s in DEV_SEEDS:
            for f in CAPS:
                cells[(s, f)] = run_cell(s, f, pool)
                print(f"  cell seed={s} cap={f} done ({time.time()-t0:.0f}s)", flush=True)
    labs = list(next(iter(cells.values())))
    print("\n## alignment: out-of-sample U/read of the class-level policy each reward would choose")
    print(f"{'policy':<22}{'U mean':>9}{'dU vs fixed':>13}{'se':>8}{'OHR':>8}{'stale%':>8}")
    base = np.array([cells[k]["fixed_best"][0] for k in cells])
    summ = {}
    for lab in labs:
        U = np.array([cells[k][lab][0] for k in cells])
        d = U - base
        se = d.std(ddof=1) / math.sqrt(len(d))
        O = np.mean([cells[k][lab][1] for k in cells]); S = np.mean([cells[k][lab][2] for k in cells]) * 100
        print(f"{lab:<22}{U.mean():9.4f}{d.mean():13.4f}{se:8.4f}{O:8.3f}{S:8.2f}")
        summ[lab] = {"U": float(U.mean()), "dU": float(d.mean()), "se": float(se)}
    out["alignment"] = summ
    Path("scratch/reward_scaling.json").write_text(json.dumps(out, indent=1))
    print(f"\n{time.time()-t0:.0f}s total")


if __name__ == "__main__":
    main()
