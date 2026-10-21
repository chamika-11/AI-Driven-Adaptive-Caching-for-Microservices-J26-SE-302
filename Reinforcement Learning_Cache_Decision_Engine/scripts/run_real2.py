"""Addendum R2: real-trace experiments on TWO clusters + the cross-trace test.

    python scripts/run_real2.py --procs 4          # resumable; writes results/real_r2.csv
Traces: c52 = Twitter cluster 52 parts 000-002 (1% key sample), c22 = cluster 22 part 000 (2% key sample).
Baselines on both traces at 1/5/25% (val+test at 1%, test otherwise); agents trained at 1% on one trace, evaluated on it AND
(test slice) on the other trace with the frozen normaliser of the training trace (the predictor tables are always fitted on the
target trace's own first 30%).
"""
import argparse
import csv
import multiprocessing as mp
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

TRACES = {"c52": "data/processed/cluster52_000-002_k1.npz", "c22": "data/processed/cluster22_000_k2.npz"}
CAPS = (0.01, 0.05, 0.25)
SEEDS = (0, 1, 2, 3, 4)
ARMS = (("dqn", "sampled_lru", ""), ("dqn_bandit", "sampled_lru", ""), ("dqn", "s3fifo", "@s3fifo"))


def _ctx(tkey, seed, cap, evict=None):
    from rlcache.evaluation import EvalContext
    from rlcache.trace.prepared import load_prepared
    return EvalContext.build(seed, cap, "harsh", trace=load_prepared(ROOT / TRACES[tkey]), base_eviction=evict)


def _train_rows(tkey, seed, variant, evict, suffix, backend, skip, decisions):
    import run_dqn as R
    from rlcache.agents import dqn_train as T
    from rlcache.baselines.policies import Spec
    from rlcache.config import DQNConfig
    from rlcache.evaluation import evaluate_sim_policy
    other = "c22" if tkey == "c52" else "c52"
    base = ("dqn:main" if variant == "dqn" else f"dqn:{variant[4:]}") + suffix
    ctx = _ctx(tkey, seed, 0.01, evict)
    need = [f"{ctx.trace_name}|dqn|{base}|harsh|cap0.01|{sp}|s{seed}" for sp in ("val", "test")]
    ctx_o = _ctx(other, seed, 0.01, evict)
    need.append(f"{ctx_o.trace_name}|dqn|{base}@from_{tkey}|harsh|cap0.01|test|s{seed}")
    if all(n in skip for n in need):
        return []
    cfg = DQNConfig()
    if decisions:
        import dataclasses
        cfg = dataclasses.replace(cfg, total_decisions=decisions, learning_starts=max(decisions // 5, 200), buffer_size=max(decisions * 2, 2000))
    t0 = time.time()
    res = T.train_dqn(ctx, R.make_learner(backend, seed, variant), cfg, gamma=R.VARIANTS[variant],
                      calib_requests=40_000 if not decisions else 4_000)
    secs = time.time() - t0
    last = res.curve[-1] if res.curve else (0, float("nan"), float("nan"), float("nan"), float("nan"))
    rows = []
    for c, name, splits, tag in ((ctx, base, ("val", "test"), "in-trace"), (ctx_o, f"{base}@from_{tkey}", ("test",), f"cross-trace from {tkey}")):
        for split in splits:
            pol = T.GreedyDQNPolicy(res, c)
            spec = Spec(name, "dqn", "learned", lambda cc, p=pol: p, eviction=c.cfg.cache.base_eviction)
            r = evaluate_sim_policy(c, spec, split, policy=pol)
            r["notes"] = (("SMOKE-TEST " if decisions else "") + f"{tag} dqn variant={variant} gamma={R.VARIANTS[variant]} backend={backend} "
                          f"trained_on={ctx.trace_name} decisions={res.decisions} epochs={res.epochs} train_s={secs:.0f} "
                          f"last_loss={last[1]:.5f} base_eviction={c.cfg.cache.base_eviction} code={R.code_hash()}")
            rows.append(r)
    return rows


def _job(args):
    kind, tkey, seed, cap, variant, evict, suffix, backend, skip, decisions = args
    if kind == "train":
        return kind, tkey, seed, cap, variant + suffix, _train_rows(tkey, seed, variant, evict, suffix, backend, skip, decisions)
    from rlcache.baselines.policies import eviction_registry, registry, s3fifo_reference_registry
    from rlcache.evaluation import evaluate
    ctx = _ctx(tkey, seed, cap)
    specs = {s.name: s for s in registry()}
    for s in eviction_registry() + s3fifo_reference_registry():
        specs.setdefault(s.name, s)
    rows = []
    for n, sp in specs.items():
        for split in (("val", "test") if cap == 0.01 else ("test",)):
            if f"{ctx.trace_name}|{sp.family}|{n}|harsh|cap{cap}|{split}|s{seed}" not in skip:
                rows.append(evaluate(ctx, sp, split))
    return kind, tkey, seed, cap, "baselines", rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--procs", type=int, default=4)
    ap.add_argument("--backend", default="torch")
    ap.add_argument("--out", default="results/real_r2.csv")
    ap.add_argument("--only", choices=("baselines", "agents", "all"), default="all")
    ap.add_argument("--decisions", type=int, default=None, help="SMOKE TEST ONLY")
    a = ap.parse_args()
    out = Path(a.out)
    skip = set()
    if out.exists():
        with open(out, newline="", encoding="utf-8") as fh:
            skip = {r["run_id"] for r in csv.DictReader(fh)}
    jobs = []
    if a.only in ("agents", "all"):
        jobs += [("train", t, s, 0.01, v, e, sfx, a.backend, skip, a.decisions) for t in TRACES for s in SEEDS for (v, e, sfx) in ARMS]
    if a.only in ("baselines", "all"):
        jobs += [("base", t, s, c, None, None, "", a.backend, skip, None) for t in TRACES for s in SEEDS for c in CAPS]
    from rlcache.results_schema import append_rows
    t0, n = time.time(), 0
    with mp.get_context("spawn").Pool(min(a.procs, len(jobs))) as pool:
        for kind, tkey, seed, cap, name, rows in pool.imap_unordered(_job, jobs):
            n += append_rows(out, rows)
            print(f"{kind} {tkey} seed {seed} cap {cap} {name}: +{len(rows)} rows ({time.time()-t0:.0f}s)", flush=True)
    print(f"wrote {n} new rows to {out} in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
