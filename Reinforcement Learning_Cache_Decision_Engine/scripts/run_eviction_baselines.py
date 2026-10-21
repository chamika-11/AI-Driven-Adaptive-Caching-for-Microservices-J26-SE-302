"""Addendum M11-E (E1) + F1: eviction baselines and the baselines-only capacity sweep.

    python scripts/run_eviction_baselines.py --procs 5      # resumable; writes results/evict_baselines.csv

Part 1: `evict:*` baselines (8 points) at the three DQN capacities (1/5/25%), val + test, seeds 0-9.
Part 2 (F1, baselines only): a fixed subset of baselines + Belady bounds at the extra capacities
        0.1% / 0.5% / 10% of the footprint, TEST slice only, seeds 0-9 (the other three capacities
        already exist in results.csv).  Rows are appended to results.csv only after a check, by hand.
"""
import argparse
import csv
import multiprocessing as mp
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

PART1_CAPS = (0.01, 0.05, 0.25)
PART2_CAPS = (0.001, 0.005, 0.10)
F1_NAMES = ("random:45", "fixed:redis/3600s/normal", "fixed:both/3600s/normal", "stat_ttl:median/redis",
            "place_size:p25", "belady_plain", "belady_ttl_constrained", "zerostale_oracle_ttl:redis")


def _job(args):
    seed, cap, part, skip = args
    from rlcache.baselines.policies import eviction_registry, registry
    from rlcache.evaluation import EvalContext, evaluate
    ctx = EvalContext.build(seed, cap, "harsh")
    reg = {s.name: s for s in registry()}
    if part == 1:
        specs, splits = eviction_registry(), ("val", "test")
    else:
        specs = [reg[n] for n in F1_NAMES] + eviction_registry()
        splits = ("test",)
    rows = []
    for sp in specs:
        for split in splits:
            rid = f"{sp.family}|{sp.name}|harsh|cap{cap}|{split}|s{seed}"
            if rid not in skip:
                rows.append(evaluate(ctx, sp, split))
    return seed, cap, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--procs", type=int, default=5)
    ap.add_argument("--out", default="results/evict_baselines.csv")
    a = ap.parse_args()
    out = Path(a.out)
    skip = set()
    if out.exists():
        with open(out, newline="", encoding="utf-8") as fh:
            skip = {r["run_id"] for r in csv.DictReader(fh)}
    jobs = [(s, c, 1, skip) for s in range(10) for c in PART1_CAPS] + \
           [(s, c, 2, skip) for s in range(10) for c in PART2_CAPS]
    from rlcache.results_schema import append_rows
    t0, n = time.time(), 0
    with mp.get_context("spawn").Pool(min(a.procs, len(jobs))) as pool:
        for seed, cap, rows in pool.imap_unordered(_job, jobs):
            n += append_rows(out, rows)
            print(f"seed {seed} cap {cap}: +{len(rows)} rows ({time.time()-t0:.0f}s)", flush=True)
    print(f"wrote {n} new rows to {out} in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
