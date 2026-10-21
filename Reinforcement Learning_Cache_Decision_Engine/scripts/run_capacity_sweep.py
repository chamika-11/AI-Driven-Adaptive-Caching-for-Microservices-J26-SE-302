"""Addendum M11-G: baselines and agents at the three remaining capacities (0.1%, 0.5%, 10%), synthetic, evaluation seeds 0-9.

    python scripts/run_capacity_sweep.py --procs 3     # resumable; writes results/capacity_sweep.csv
Rows already present in results/results.csv (the F1 baseline subset, test slice) are skipped, never overwritten.
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

CAPS = (0.001, 0.005, 0.10)
SEEDS = tuple(range(10))
ARMS = ("dqn", "dqn_bandit")


def _job(args):
    kind, seed, cap, variant, backend, skip, decisions = args
    from rlcache.evaluation import EvalContext
    ctx = EvalContext.build(seed, cap, "harsh")
    if kind == "train":
        import run_dqn as R
        name = "dqn:main" if variant == "dqn" else f"dqn:{variant[4:]}"
        if all(f"dqn|{name}|harsh|cap{cap}|{sp}|s{seed}" in skip for sp in ("val", "test")):
            return kind, seed, cap, name, []
        return kind, seed, cap, name, R.dqn_rows(ctx, variant, backend, None, decisions)
    from rlcache.baselines.policies import eviction_registry, registry
    from rlcache.evaluation import evaluate
    specs = {s.name: s for s in registry()}
    for s in eviction_registry():
        specs.setdefault(s.name, s)
    rows = []
    for n, sp in specs.items():
        for split in ("val", "test"):
            if f"{sp.family}|{n}|harsh|cap{cap}|{split}|s{seed}" not in skip:
                rows.append(evaluate(ctx, sp, split))
    return kind, seed, cap, "baselines", rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--procs", type=int, default=3)
    ap.add_argument("--backend", default="torch")
    ap.add_argument("--out", default="results/capacity_sweep.csv")
    ap.add_argument("--decisions", type=int, default=None, help="SMOKE TEST ONLY")
    a = ap.parse_args()
    out = Path(a.out)
    skip = set()
    for f in (out, ROOT / "results" / "results.csv"):
        if f.exists():
            with open(f, newline="", encoding="utf-8") as fh:
                skip |= {r["run_id"] for r in csv.DictReader(fh)}
    jobs = [("base", s, c, None, a.backend, skip, None) for s in SEEDS for c in CAPS]
    jobs += [("train", s, c, v, a.backend, skip, a.decisions) for s in SEEDS for c in CAPS for v in ARMS]
    from rlcache.results_schema import append_rows
    t0, n = time.time(), 0
    with mp.get_context("spawn").Pool(min(a.procs, len(jobs))) as pool:
        for kind, seed, cap, name, rows in pool.imap_unordered(_job, jobs):
            n += append_rows(out, rows)
            print(f"{kind} seed {seed} cap {cap} {name}: +{len(rows)} rows ({time.time()-t0:.0f}s)", flush=True)
    print(f"wrote {n} new rows to {out} in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
