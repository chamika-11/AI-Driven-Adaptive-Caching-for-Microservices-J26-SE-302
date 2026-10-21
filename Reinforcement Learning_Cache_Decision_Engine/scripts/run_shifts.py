"""Addendum M11-E (E3): workload-shift experiments.  One job = (shift, seed): train dqn / dqn_bandit on the pre-shift
world, evaluate FROZEN and ONLINE on the test slice that contains the shift, plus the non-learned policies.

    python scripts/run_shifts.py --procs 5          # resumable; writes results/shift/<shift>_s<seed>.json
"""
import argparse
import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

CAP = 0.01
NONLEARNED = ("place_size:p25", "fixed:redis/3600s/normal", "random:45", "stat_ttl:median/redis",
              "aimd:a60/b0.5", "aimd:a300/b0.25", "evict:sieve/redis/3600s", "evict:s3fifo/redis/3600s",
              "evict:lru/redis/3600s")


def _job(args):
    shift, seed, backend, outdir, decisions = args
    out = Path(outdir) / f"{shift}_s{seed}.json"
    if out.exists():
        return shift, seed, "skipped"
    import run_dqn as R
    from rlcache import shift as SH
    from rlcache.agents import dqn_train as T
    from rlcache.baselines.policies import eviction_registry, registry
    from rlcache.config import DQNConfig
    from rlcache.evaluation import EvalContext
    tr = SH.make_shift_trace(shift, seed)
    ctx = EvalContext.build(seed, CAP, "harsh", trace=tr)
    t_star, a = SH.shift_index(tr), ctx.slice_for("test")[0]
    reg = {s.name: s for s in registry() + eviction_registry()}
    series = {}
    for n in NONLEARNED:
        sp = reg[n]
        series[n] = SH.series_for_policy(ctx, sp.make(ctx), eviction=sp.eviction)
    cfg = DQNConfig()
    if decisions:
        import dataclasses
        cfg = dataclasses.replace(cfg, total_decisions=decisions, learning_starts=max(decisions // 5, 200),
                                  buffer_size=max(decisions * 2, 2000))
    for variant in ("dqn", "dqn_bandit"):
        name = "dqn:main" if variant == "dqn" else "dqn:bandit"
        res = T.train_dqn(ctx, R.make_learner(backend, seed, variant), cfg, gamma=R.VARIANTS[variant],
                          calib_requests=40_000 if not decisions else 4_000)
        series[name + ":frozen"] = SH.series_for_policy(ctx, T.GreedyDQNPolicy(res, ctx))
        series[name + ":online"] = SH.series_online(ctx, res, cfg, learning_starts=2_000 if not decisions else 300)
    meta = {"shift": shift, "seed": seed, "t_star": t_star, "test_start": a, "window": SH.WINDOW,
            "capacity": CAP, "backend": backend, "smoke": bool(decisions), "n_requests": len(tr),
            "code": R.code_hash()}
    Path(outdir).mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"meta": meta, "series": series}), encoding="utf-8")
    return shift, seed, "done"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--procs", type=int, default=5)
    ap.add_argument("--backend", default="torch")
    ap.add_argument("--out", default="results/shift")
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2, 3, 4])
    ap.add_argument("--shifts", nargs="+", default=["perm", "flash", "diurnal", "write10"])
    ap.add_argument("--decisions", type=int, default=None, help="SMOKE TEST ONLY")
    a = ap.parse_args()
    jobs = [(sh, s, a.backend, a.out, a.decisions) for s in a.seeds for sh in a.shifts]
    t0 = time.time()
    with mp.get_context("spawn").Pool(min(a.procs, len(jobs))) as pool:
        for sh, s, st in pool.imap_unordered(_job, jobs):
            print(f"{sh} seed {s}: {st} ({time.time()-t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
