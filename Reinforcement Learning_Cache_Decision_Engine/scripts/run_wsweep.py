"""Addendum M11-E (E2): w_stale sweep at the primary capacity.  Specified architecture, evaluation seeds 0-9.

    python scripts/run_wsweep.py --procs 5      # resumable; appends to results/dqn_wsweep.csv
w_stale = 3 is NOT re-run: those rows already exist as `dqn:main` (Addendum M9 evaluation run).
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

CAP = 0.01
WEIGHTS = (1.5, 2.0, 5.0, 10.0)


def _job(args):
    seed, w, backend, skip = args
    import run_dqn as R
    from rlcache.evaluation import EvalContext
    suffix = f"@w{w:g}"
    name = "dqn:main" + suffix
    if all(f"dqn|{name}|harsh|cap{CAP}|{sp}|s{seed}" in skip for sp in ("val", "test")):
        return seed, w, []
    ctx = EvalContext.build(seed, CAP, "harsh", w_stale=w)
    rows = R.dqn_rows(ctx, "dqn", backend, None, None, suffix=suffix)
    for r in rows:
        r["notes"] += f" w_stale={w:g} (Addendum M11-E E2)"
    return seed, w, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--procs", type=int, default=5)
    ap.add_argument("--backend", default="torch")
    ap.add_argument("--out", default="results/dqn_wsweep.csv")
    ap.add_argument("--seeds", type=int, nargs="+", default=list(range(10)))
    a = ap.parse_args()
    out = Path(a.out)
    skip = set()
    if out.exists():
        with open(out, newline="", encoding="utf-8") as fh:
            skip = {r["run_id"] for r in csv.DictReader(fh)}
    jobs = [(s, w, a.backend, skip) for s in a.seeds for w in WEIGHTS]
    from rlcache.results_schema import append_rows
    t0, n = time.time(), 0
    with mp.get_context("spawn").Pool(min(a.procs, len(jobs))) as pool:
        for seed, w, rows in pool.imap_unordered(_job, jobs):
            n += append_rows(out, rows)
            print(f"seed {seed} w_stale {w:g}: +{len(rows)} rows ({time.time()-t0:.0f}s)", flush=True)
    print(f"wrote {n} new rows to {out} in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
