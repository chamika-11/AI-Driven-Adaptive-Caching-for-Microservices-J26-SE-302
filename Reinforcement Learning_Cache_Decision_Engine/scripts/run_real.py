"""Addendum R1: first real-trace experiment (Twitter cluster 52, part 000, 1% key sample).

    python scripts/run_real.py --procs 5         # resumable; writes results/real_cluster52.csv
Baselines at 1/5/25% (val+test at 1%, test only otherwise) and the agents ONLY at 1% (dqn:main, dqn:bandit, dqn:main@s3fifo).
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

TRACE = "data/processed/cluster52_000_k1.npz"
CAPS = (0.01, 0.05, 0.25)
SEEDS = (0, 1, 2, 3, 4)
ARMS = (("dqn", "sampled_lru", ""), ("dqn_bandit", "sampled_lru", ""), ("dqn", "s3fifo", "@s3fifo"))


def _ctx(seed, cap, evict=None):
    from rlcache.evaluation import EvalContext
    from rlcache.trace.prepared import load_prepared
    return EvalContext.build(seed, cap, "harsh", trace=load_prepared(ROOT / TRACE), base_eviction=evict)


def _job(args):
    kind, seed, cap, variant, evict, suffix, backend, skip, decisions = args
    if kind == "train":
        import run_dqn as R
        name = ("dqn:main" if variant == "dqn" else f"dqn:{variant[4:]}") + suffix
        ctx = _ctx(seed, cap, evict)
        if all(f"{ctx.trace_name}|dqn|{name}|harsh|cap{cap}|{sp}|s{seed}" in skip for sp in ("val", "test")):
            return kind, seed, cap, name, []
        return kind, seed, cap, name, R.dqn_rows(ctx, variant, backend, None, decisions, suffix=suffix)
    from rlcache.baselines.policies import eviction_registry, registry, s3fifo_reference_registry
    from rlcache.evaluation import evaluate
    ctx = _ctx(seed, cap)
    specs = {s.name: s for s in registry()}
    for s in eviction_registry() + s3fifo_reference_registry():
        specs.setdefault(s.name, s)
    rows = []
    for n, sp in specs.items():
        for split in (("val", "test") if cap == 0.01 else ("test",)):
            if f"{ctx.trace_name}|{sp.family}|{n}|harsh|cap{cap}|{split}|s{seed}" not in skip:
                rows.append(evaluate(ctx, sp, split))
    return kind, seed, cap, "baselines", rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--procs", type=int, default=5)
    ap.add_argument("--backend", default="torch")
    ap.add_argument("--out", default="results/real_cluster52.csv")
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
        jobs += [("train", s, 0.01, v, e, sfx, a.backend, skip, a.decisions) for s in SEEDS for (v, e, sfx) in ARMS]
    if a.only in ("baselines", "all"):
        jobs += [("base", s, c, None, None, None, a.backend, skip, None) for s in SEEDS for c in CAPS]
    from rlcache.results_schema import append_rows
    t0, n = time.time(), 0
    with mp.get_context("spawn").Pool(min(a.procs, len(jobs))) as pool:
        for kind, seed, cap, name, rows in pool.imap_unordered(_job, jobs):
            n += append_rows(out, rows)
            print(f"{kind} seed {seed} cap {cap} {name}: +{len(rows)} rows ({time.time()-t0:.0f}s)", flush=True)
    print(f"wrote {n} new rows to {out} in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
