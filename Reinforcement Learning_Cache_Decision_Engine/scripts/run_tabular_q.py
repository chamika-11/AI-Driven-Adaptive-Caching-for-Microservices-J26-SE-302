"""One-time evaluation-seed run of the tabular Q variants (pre-registered, Addendum M8).

    python scripts/run_tabular_q.py                # seeds 0-9, caps 1/5/25%, qbin/ewidth/bandit

Appends schema rows (policy_class = learned, family = tabular_q) to results/results.csv.
Idempotent on run_id.  Hyper-parameters are those frozen in the pre-registration; do not edit.
"""
import argparse
import csv
import sys
import time
from multiprocessing import Pool
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
sys.path.insert(0, str(HERE))
from rlcache.evaluation import EvalContext  # noqa: E402
from rlcache.results_schema import append_rows  # noqa: E402
from tabq_gate import VARIANTS, tabq_rows  # noqa: E402


def _job(args):
    seed, cap, variants, skip = args
    ctx = EvalContext.build(seed, cap, "harsh")
    rows = []
    for v in variants:
        if all(f"tabular_q|tabq:{v}|harsh|cap{cap}|{sp}|s{seed}" in skip for sp in ("val", "test")):
            continue
        rows += tabq_rows(ctx, v)
    return seed, cap, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=list(range(10)))
    ap.add_argument("--capacities", type=float, nargs="+", default=[0.01, 0.05, 0.25])
    ap.add_argument("--variants", nargs="+", default=list(VARIANTS))
    ap.add_argument("--out", default="results/results.csv")
    ap.add_argument("--procs", type=int, default=10)
    a = ap.parse_args()
    out = Path(a.out)
    existing = set()
    if out.exists():
        with open(out, newline="", encoding="utf-8") as fh:
            existing = {r["run_id"] for r in csv.DictReader(fh)}
    jobs = [(s, c, a.variants, existing) for s in a.seeds for c in a.capacities]
    t0, n = time.time(), 0
    with Pool(min(a.procs, len(jobs))) as pool:
        for seed, cap, rows in pool.imap_unordered(_job, jobs):
            n += append_rows(out, rows)
            print(f"seed {seed} cap {cap}: +{len(rows)} rows ({time.time()-t0:.0f}s)", flush=True)
    print(f"wrote {n} new rows to {out} in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
