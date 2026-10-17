"""C-37 investigation: does the placement dimension carry signal under the spec's objective?

Utility per read (the spec's read-level reward terms; backend/memory terms are monotone in hits
and omitted so the comparison is not hostage to their unfinished scaling):

    U = w_hit * 1{hit} + w_lat * exp(-L / L0) - w_stale * min(1, stale_age / ttl_chosen)

Sub-commands
------------
scan     fixed placement x one TTL across regimes (capacity, tier ratio, staleness, L0, alpha)
classes  does per-class placement (fit on the FIRST half, scored on the SECOND half) add value
         beyond per-class TTL?  Compares against the best single fixed action.

Synthetic data only; nothing here is a real-trace result.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import math
import sys
import time
from dataclasses import dataclass
from functools import lru_cache
from multiprocessing import Pool
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from rlcache.actions import decode_action, encode_action  # noqa: E402
from rlcache.config import Config, StalenessConfig, TTL_BUCKETS_S, WorkloadConfig  # noqa: E402
from rlcache.predictor.standin import compute_volatility  # noqa: E402
from rlcache.sim.engine import Simulator  # noqa: E402
from rlcache.sim.policy import FixedActionPolicy  # noqa: E402
from rlcache.trace.synthetic import generate_synthetic  # noqa: E402

W_HIT, W_LAT, W_STALE = 1.0, 0.5, 3.0
PLACEMENTS = ("local", "redis", "both")


@dataclass(frozen=True)
class Regime:
    name: str
    frac: float = 0.25            # L2 as a fraction of the unique-object footprint
    ratio: float = 0.10           # L1 as a fraction of L2
    p_inv: float = 0.5            # P(L1 copy invalidated on a write)
    d_inv: float = 2.0            # L1 invalidation delay (s)
    p_bypass: float = 0.05        # P(write skips invalidation of both tiers)
    l0_us: float = 8000.0         # L0 in exp(-L/L0)
    alpha: float = 0.99           # Zipf skew
    mode: str = "lossy"           # staleness mode: lossy | ttl_only | perfect
    n_requests: int = 600_000
    n_keys: int = 4_000


def make_cfg(r: Regime) -> Config:
    c = Config()
    cache = dataclasses.replace(c.cache, l2_footprint_frac=r.frac, l1_fraction_of_l2=r.ratio)
    lat = dataclasses.replace(c.latency, l0_us=r.l0_us)
    return dataclasses.replace(c, cache=cache, latency=lat,
                               staleness=StalenessConfig(r.mode, r.p_inv, r.d_inv, r.p_bypass))


@lru_cache(maxsize=16)
def get_trace(seed: int, alpha: float, n_requests: int, n_keys: int):
    return generate_synthetic(WorkloadConfig(seed=seed, zipf_alpha=alpha,
                                             n_requests=n_requests, n_keys=n_keys))


class ClassPolicy:
    """Action chosen by the key's class (a stand-in for 'what a feature-based agent could learn')."""

    def __init__(self, cls_of_key: np.ndarray, action_of_class: np.ndarray):
        self.cls, self.act = cls_of_key.tolist(), action_of_class.tolist()

    def decide(self, ctx) -> int:
        return self.act[self.cls[ctx.key]]


def agg_run(seed: int, r: Regime, policy, a: int, b: int, sim_seed: int = 0) -> dict:
    """Run [a, b) cold and return per-key aggregates of the utility ingredients."""
    tr = get_trace(seed, r.alpha, r.n_requests, r.n_keys)
    n_keys = tr.n_keys
    hits = np.zeros(n_keys); lat = np.zeros(n_keys); stc = np.zeros(n_keys); miss = np.zeros(n_keys)
    stale = np.zeros(n_keys)

    def sink(ins):
        k = ins.key
        hits[k] += ins.hits; lat[k] += ins.lat_score_sum; stc[k] += ins.stale_cost_sum
        miss[k] += ins.concurrent; stale[k] += ins.stale

    cfg = make_cfg(r)
    sim = Simulator(tr, cfg, policy, seed=sim_seed, keep_closed=False, record_latencies=False,
                    sink=sink)
    sim.run(start=a, end=b, measure_from=a)
    miss_score = math.exp(-cfg.latency.backend_us / cfg.latency.l0_us)
    u_k = W_HIT * hits + W_LAT * (lat + miss_score * miss) - W_STALE * stc
    reads = hits + miss
    return {"u_k": u_k, "reads_k": reads, "hits_k": hits, "stale_k": stale,
            "U": float(u_k.sum() / reads.sum()), "ohr": float(hits.sum() / reads.sum()),
            "stale_rate": float(stale.sum() / reads.sum())}


# ---- scan -----------------------------------------------------------------------------------
def _scan_job(args):
    seed, r, p, t = args
    out = agg_run(seed, r, FixedActionPolicy.of(p, t, 1), 0, r.n_requests)
    return (r.name, seed, p, t, out["U"], out["ohr"], out["stale_rate"])


def regimes_for_scan() -> list[Regime]:
    out = []
    for frac in (0.05, 0.25):
        for ratio in (0.05, 0.25):
            for st_name, (pi, di, pb) in (("lossy", (0.5, 2.0, 0.05)), ("instantL1", (1.0, 0.0, 0.0))):
                for l0 in (8000.0, 300.0):
                    out.append(Regime(f"cap{frac}_r{ratio}_{st_name}_L0{int(l0)}", frac, ratio,
                                      pi, di, pb, l0))
    return out


def cmd_scan(args):
    seeds = list(range(args.seeds))
    ttl_idx = args.ttl_idx
    regs = regimes_for_scan()
    jobs = [(s, r, p, ttl_idx) for r in regs for s in seeds for p in range(3)]
    t0 = time.time()
    with Pool(args.procs) as pool:
        res = pool.map(_scan_job, jobs, chunksize=1)
    tab: dict = {}
    for name, s, p, t, U, ohr, st in res:
        tab.setdefault(name, {}).setdefault(s, {})[p] = (U, ohr, st)
    print(f"# scan: TTL = {TTL_BUCKETS_S[ttl_idx]} s, seeds = {len(seeds)}, {time.time()-t0:.0f}s wall")
    print(f"{'regime':<34}{'U redis':>9}{'dU both':>10}{'+-sd':>7}{'dU local':>10}{'+-sd':>7}"
          f"{'best':>7}{'  OHR r/b/l':>20}{'  stale% r/b/l':>22}")
    summary = {}
    for name, per_seed in tab.items():
        U = np.array([[per_seed[s][p][0] for p in range(3)] for s in seeds])    # (seeds, 3)
        O = np.array([[per_seed[s][p][1] for p in range(3)] for s in seeds]).mean(0)
        S = np.array([[per_seed[s][p][2] for p in range(3)] for s in seeds]).mean(0) * 100
        d_both, d_loc = U[:, 2] - U[:, 1], U[:, 0] - U[:, 1]
        best = PLACEMENTS[int(U.mean(0).argmax())]
        print(f"{name:<34}{U[:,1].mean():9.4f}{d_both.mean():10.4f}{d_both.std(ddof=1):7.4f}"
              f"{d_loc.mean():10.4f}{d_loc.std(ddof=1):7.4f}{best:>7}"
              f"   {O[1]:.3f}/{O[2]:.3f}/{O[0]:.3f}   {S[1]:5.2f}/{S[2]:5.2f}/{S[0]:5.2f}")
        summary[name] = {"U": U.mean(0).tolist(), "d_both": [float(d_both.mean()), float(d_both.std(ddof=1))],
                         "d_local": [float(d_loc.mean()), float(d_loc.std(ddof=1))], "best": best}
    Path(args.out).write_text(json.dumps(summary, indent=1))


# ---- classes ----------------------------------------------------------------------------------
ACTS = [encode_action(p, t, 1) for p in range(3) for t in range(5)]


def _terciles(x: np.ndarray, mask: np.ndarray) -> np.ndarray:
    q = np.quantile(x[mask], [1 / 3, 2 / 3])
    return np.digitize(x, q)                                   # 0,1,2


def build_classes(tr, mid: int):
    """Class = popularity tercile x volatility tercile, from the FIRST half only (features an
    agent could see: request counts and the R-P1 volatility).  Unseen keys -> class 9."""
    seg = tr.slice(0, mid)
    reads = np.bincount(seg.key[seg.is_read], minlength=tr.n_keys).astype(float)
    vol = compute_volatility(seg).astype(float)
    seen = reads >= 1
    cls = np.full(tr.n_keys, 9, dtype=np.int64)
    pop_t = _terciles(reads, seen)
    vol_t = _terciles(vol + 1e-9 * np.arange(tr.n_keys) / tr.n_keys, seen)   # break ties
    cls[seen] = pop_t[seen] * 3 + vol_t[seen]
    return cls, reads


def _train_job(args):
    seed, r, act, a, b = args
    o = agg_run(seed, r, FixedActionPolicy(act), a, b)
    return act, o["u_k"], o["reads_k"], o["ohr"], o["stale_rate"]


def _eval_job(args):
    seed, r, cls, act_of_class, a, b, label = args
    o = agg_run(seed, r, ClassPolicy(cls, act_of_class), a, b)
    return label, o["U"], o["ohr"], o["stale_rate"]


def class_experiment(seed: int, r: Regime, pool: Pool) -> dict:
    tr = get_trace(seed, r.alpha, r.n_requests, r.n_keys)
    n = len(tr)
    mid = n // 2
    cls, reads1 = build_classes(tr, mid)
    n_cls = 10
    train = pool.map(_train_job, [(seed, r, a, 0, mid) for a in ACTS], chunksize=1)
    u_key = {a: u for a, u, *_ in train}                       # per-key utility sums (train)
    u_cls = {a: np.bincount(cls, weights=u_key[a], minlength=n_cls) for a in ACTS}
    tot = {a: float(u_key[a].sum()) for a in ACTS}
    a_star = max(ACTS, key=lambda a: tot[a])
    p_star, t_star, _ = decode_action(a_star)

    def pick(allowed):
        out = np.full(n_cls, a_star, dtype=np.int64)
        for c in range(n_cls - 1):
            best = max(allowed, key=lambda a: u_cls[a][c])
            if u_cls[best][c] > u_cls[a_star][c] + 1e-9:
                out[c] = best
        return out

    ttl_only = pick([a for a in ACTS if decode_action(a).placement == p_star])
    place_only = pick([a for a in ACTS if decode_action(a).ttl_idx == t_star])
    joint = pick(ACTS)

    # identity-level (per key) variants, only for keys with enough train reads
    def pick_key(allowed):
        act = np.full(tr.n_keys, a_star, dtype=np.int64)
        elig = reads1 >= 20
        mat = np.stack([u_key[a] for a in allowed])             # (A, n_keys)
        best = np.array(allowed)[mat.argmax(0)]
        gain = mat.max(0) > u_key[a_star] + 1e-9
        act[elig & gain] = best[elig & gain]
        return act

    id_ttl = pick_key([a for a in ACTS if decode_action(a).placement == p_star])
    id_place = pick_key([a for a in ACTS if decode_action(a).ttl_idx == t_star])
    id_joint = pick_key(ACTS)

    ident = np.arange(tr.n_keys)
    evals = [
        ("fixed_best", cls, np.full(n_cls, a_star)),
        ("class_ttl_only", cls, ttl_only), ("class_place_only", cls, place_only),
        ("class_joint", cls, joint),
        ("key_ttl_only", ident, id_ttl), ("key_place_only", ident, id_place),
        ("key_joint", ident, id_joint),
    ]
    # best fixed action restricted to each placement, evaluated out of sample
    for p in range(3):
        ap = max([a for a in ACTS if decode_action(a).placement == p], key=lambda a: tot[a])
        evals.append((f"fixed_best_{PLACEMENTS[p]}", cls, np.full(n_cls, ap)))
    ev = pool.map(_eval_job, [(seed, r, c, a, mid, n, lab) for lab, c, a in evals], chunksize=1)
    res = {lab: (U, ohr, st) for lab, U, ohr, st in ev}
    # in-sample class-level optimism (train segment): sum_c max_a U_c(a) vs the fixed best
    def insample(allowed):
        return sum(max(u_cls[a][c] for a in allowed) for c in range(n_cls - 1)) \
            + u_cls[a_star][9]
    reads_tot = sum(np.bincount(cls, weights=train[0][2], minlength=n_cls))
    return {"a_star": int(a_star), "a_star_desc": f"{PLACEMENTS[p_star]}/{TTL_BUCKETS_S[t_star]}s",
            "res": res, "classes_used": {"ttl": int((ttl_only != a_star).sum()),
                                         "place": int((place_only != a_star).sum()),
                                         "joint": int((joint != a_star).sum())},
            "insample_gain": {"ttl": (insample([a for a in ACTS if decode_action(a).placement == p_star]) - tot[a_star]) / reads_tot,
                              "place": (insample([a for a in ACTS if decode_action(a).ttl_idx == t_star]) - tot[a_star]) / reads_tot,
                              "joint": (insample(ACTS) - tot[a_star]) / reads_tot},
            "ttl_choice_by_class": [TTL_BUCKETS_S[decode_action(int(a)).ttl_idx] for a in joint],
            "place_choice_by_class": [PLACEMENTS[decode_action(int(a)).placement] for a in joint]}


def cmd_classes(args):
    regs = {r.name: r for r in [
        Regime("default"),                                         # capacity 25%, lossy, L0 = backend
        Regime("cap5", frac=0.05),
        Regime("friendly", frac=0.05, ratio=0.25, p_inv=1.0, d_inv=0.0, p_bypass=0.0, l0_us=300.0),
        Regime("zipf1.2", alpha=1.2),
        Regime("ratio25", ratio=0.25),                              # spec L0, big sidecar, lossy L1
        Regime("ratio25_L0300", ratio=0.25, l0_us=300.0),           # same, latency at tier scale
        Regime("ttl_only", mode="ttl_only"),                        # no invalidation anywhere
        Regime("harsh", p_inv=0.2, d_inv=10.0, p_bypass=0.3),       # unreliable invalidation
    ]}
    names = args.regimes or list(regs)
    out = {}
    with Pool(args.procs) as pool:
        for name in names:
            r = regs[name]
            per_seed = []
            t0 = time.time()
            for s in range(args.seeds):
                per_seed.append(class_experiment(s, r, pool))
            labs = list(per_seed[0]["res"])
            print(f"\n## regime {name}: {r}   ({time.time()-t0:.0f}s)")
            print("best single fixed action on train:", [p["a_star_desc"] for p in per_seed])
            print(f"{'policy (evaluated on 2nd half)':<26}{'U/read':>9}{'dU vs fixed':>13}{'+-sd':>8}"
                  f"{'OHR':>8}{'stale%':>8}")
            base = np.array([p["res"]["fixed_best"][0] for p in per_seed])
            summ = {}
            for lab in labs:
                U = np.array([p["res"][lab][0] for p in per_seed])
                O = np.mean([p["res"][lab][1] for p in per_seed])
                S = np.mean([p["res"][lab][2] for p in per_seed]) * 100
                d = U - base
                print(f"{lab:<26}{U.mean():9.4f}{d.mean():13.4f}{(d.std(ddof=1) if len(d)>1 else 0):8.4f}"
                      f"{O:8.3f}{S:8.2f}")
                summ[lab] = {"U": float(U.mean()), "dU": float(d.mean()),
                             "sd": float(d.std(ddof=1)) if len(d) > 1 else 0.0}
            inc = np.array([p["res"]["class_joint"][0] - p["res"]["class_ttl_only"][0] for p in per_seed])
            print(f"incremental value of placement on top of per-class TTL (class_joint - class_ttl_only): "
                  f"{inc.mean():.4f} +- {inc.std(ddof=1) if len(inc)>1 else 0:.4f}")
            print("in-sample class gains (train):", {k: round(float(np.mean([p['insample_gain'][k] for p in per_seed])), 4)
                                                       for k in ("ttl", "place", "joint")})
            print("joint choice by class (seed 0):", list(zip(per_seed[0]["place_choice_by_class"],
                                                             per_seed[0]["ttl_choice_by_class"])))
            out[name] = {"summary": summ, "incremental_place": [float(inc.mean()),
                         float(inc.std(ddof=1)) if len(inc) > 1 else 0.0]}
    Path(args.out).write_text(json.dumps(out, indent=1))


# ---- oracle upper bounds ------------------------------------------------------------------------
@lru_cache(maxsize=16)
def get_oracle(seed: int, alpha: float, n_requests: int, n_keys: int):
    from rlcache.trace.oracle import annotate_oracle
    return annotate_oracle(get_trace(seed, alpha, n_requests, n_keys))


class OraclePolicy:
    """Uses the FUTURE (time to the key's next write): a BOUND, never a baseline (R-D8).

    ttl:   largest bucket <= time-to-next-write (5 s if shorter; 3600 s if never rewritten)
    place: 'both' if no write lands inside the chosen TTL else 'redis' (keep volatile keys out
           of the sidecar, where invalidation is lossy)
    """

    def __init__(self, nw_ttl: np.ndarray, use_ttl: bool, use_place: bool, p_star: int, t_star: int):
        self.nw, self.use_ttl, self.use_place = nw_ttl, use_ttl, use_place
        self.p_star, self.t_star = p_star, t_star

    def decide(self, ctx) -> int:
        tnw = self.nw[ctx.idx] - ctx.ts
        t = self.t_star
        if self.use_ttl:
            t = 0
            for j, b in enumerate(TTL_BUCKETS_S):
                if tnw >= b:
                    t = j
        p = self.p_star
        if self.use_place:
            p = 2 if tnw > TTL_BUCKETS_S[t] + 0.05 else 1
        return encode_action(p, t, 1)


def _oracle_job(args):
    seed, r, kind, p_star, t_star = args
    orc = get_oracle(seed, r.alpha, r.n_requests, r.n_keys)
    pol = OraclePolicy(orc.next_write_ts, kind in ("ttl", "joint"), kind in ("place", "joint"),
                       p_star, t_star)
    o = agg_run(seed, r, pol, 0, r.n_requests)
    return kind, o["U"], o["ohr"], o["stale_rate"]


def cmd_oracle(args):
    regs = {r.name: r for r in [
        Regime("default"), Regime("cap5", frac=0.05),
        Regime("ratio25", ratio=0.25), Regime("ratio25_L0300", ratio=0.25, l0_us=300.0),
        Regime("friendly", frac=0.05, ratio=0.25, p_inv=1.0, d_inv=0.0, p_bypass=0.0, l0_us=300.0),
        Regime("ttl_only", mode="ttl_only"), Regime("harsh", p_inv=0.2, d_inv=10.0, p_bypass=0.3),
    ]}
    names = args.regimes or list(regs)
    out = {}
    with Pool(args.procs) as pool:
        for name in names:
            r = regs[name]
            rows = {k: [] for k in ("fixed", "ttl", "place", "joint")}
            ohr = {k: [] for k in rows}
            stl = {k: [] for k in rows}
            for s in range(args.seeds):
                grid = pool.map(_train_job, [(s, r, a, 0, r.n_requests) for a in ACTS], chunksize=1)
                tot = {a: float(u.sum() / rd.sum()) for a, u, rd, *_ in grid}
                a_star = max(ACTS, key=lambda a: tot[a])
                p_star, t_star, _ = decode_action(a_star)
                ev = {a: (o, st) for a, _, _, o, st in grid}
                rows["fixed"].append(tot[a_star]); ohr["fixed"].append(ev[a_star][0])
                stl["fixed"].append(ev[a_star][1])
                res = pool.map(_oracle_job, [(s, r, k, p_star, t_star) for k in ("ttl", "place", "joint")])
                for k, U, o, st in res:
                    rows[k].append(U); ohr[k].append(o); stl[k].append(st)
            base = np.array(rows["fixed"])
            print(f"\n## oracle bounds, regime {name}: {r}")
            print(f"{'policy (full trace)':<26}{'U/read':>9}{'dU vs fixed':>13}{'+-sd':>8}{'OHR':>8}{'stale%':>8}")
            summ = {}
            for k in ("fixed", "ttl", "place", "joint"):
                U = np.array(rows[k]); d = U - base
                lab = {"fixed": "fixed_best", "ttl": "zerostale_TTL(future)", "place": "volatility_place(future)",
                       "joint": "both_of_the_above"}[k]
                print(f"{lab:<26}{U.mean():9.4f}{d.mean():13.4f}"
                      f"{(d.std(ddof=1) if len(d) > 1 else 0):8.4f}{np.mean(ohr[k]):8.3f}{100*np.mean(stl[k]):8.2f}")
                summ[k] = {"U": float(U.mean()), "dU": float(d.mean())}
            out[name] = summ
    Path(args.out).write_text(json.dumps(out, indent=1))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan"); s.add_argument("--seeds", type=int, default=3)
    s.add_argument("--ttl-idx", type=int, default=3); s.add_argument("--procs", type=int, default=10)
    s.add_argument("--out", default="scratch/placement_scan.json"); s.set_defaults(fn=cmd_scan)
    c = sub.add_parser("classes"); c.add_argument("--seeds", type=int, default=3)
    c.add_argument("--procs", type=int, default=10); c.add_argument("--regimes", nargs="*")
    c.add_argument("--out", default="scratch/placement_classes.json"); c.set_defaults(fn=cmd_classes)
    o = sub.add_parser("oracle"); o.add_argument("--seeds", type=int, default=3)
    o.add_argument("--procs", type=int, default=10); o.add_argument("--regimes", nargs="*")
    o.add_argument("--out", default="scratch/placement_oracle.json"); o.set_defaults(fn=cmd_oracle)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
