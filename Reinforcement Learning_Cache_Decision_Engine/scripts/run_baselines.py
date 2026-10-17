"""Run the frozen M6 baseline set and append schema-validated rows to a results CSV.

    python scripts/run_baselines.py --seeds 0 1 2 ... 9 --capacities 0.01 0.05 0.25 \
        --splits val test --out results/results.csv

Idempotent: rows whose run_id already exists are skipped, so the test split is computed once
per (policy, seed, capacity).  Use ``--out results/dev_results.csv`` with development seeds
(>= 100) while debugging; never mix dev seeds into results.csv.
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from rlcache.baselines.policies import registry  # noqa: E402
from rlcache.evaluation import EvalContext, evaluate  # noqa: E402
from rlcache.results_schema import append_rows  # noqa: E402


def _job(args):
    seed, cap, arm, splits, families, skip = args
    ctx = EvalContext.build(seed, cap, arm)
    rows = []
    for spec in registry():
        if families and spec.family not in families:
            continue
        for split in splits:
            rid = f"{spec.family}|{spec.name}|{arm}|cap{cap}|{split}|s{seed}"
            if rid in skip:
                continue
            rows.append(evaluate(ctx, spec, split))
    return seed, cap, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=list(range(10)))
    ap.add_argument("--capacities", type=float, nargs="+", default=[0.01, 0.05, 0.25])
    ap.add_argument("--splits", nargs="+", default=["val", "test"])
    ap.add_argument("--arm", default="harsh")
    ap.add_argument("--families", nargs="*", default=None)
    ap.add_argument("--procs", type=int, default=10)
    ap.add_argument("--out", default="results/results.csv")
    a = ap.parse_args()
    out = Path(a.out)
    existing: set[str] = set()
    if out.exists():
        with open(out, newline="", encoding="utf-8") as fh:
            existing = {r["run_id"] for r in csv.DictReader(fh)}
    jobs = [(s, c, a.arm, a.splits, a.families, existing) for s in a.seeds for c in a.capacities]
    t0 = time.time()
    n = 0
    with Pool(min(a.procs, len(jobs))) as pool:
        for seed, cap, rows in pool.imap_unordered(_job, jobs):
            n += append_rows(out, rows)
            print(f"seed {seed} cap {cap}: +{len(rows)} rows ({time.time()-t0:.0f}s)", flush=True)
    print(f"wrote {n} new rows to {out} in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
