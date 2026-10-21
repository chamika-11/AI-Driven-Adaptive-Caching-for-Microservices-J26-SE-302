"""Addendum M11-F: the agent on top of S3-FIFO base eviction - development run, seeds 120-129, 1% capacity, VALIDATION slice only.

    python scripts/run_s3_dev.py --procs 5      # resumable; writes results/dqn_s3_dev.csv (never appended to results.csv)
Jobs: 30 trainings (dqn:main@s3fifo, dqn:bandit@s3fifo, dqn:main on sampled LRU) + 10 reference jobs (all non-learned points).
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
SEEDS = tuple(range(120, 130))
ARMS = (("dqn", "s3fifo", "@s3fifo"), ("dqn_bandit", "s3fifo", "@s3fifo"), ("dqn", "sampled_lru", ""))


def _job(args):
    kind, seed, variant, evict, suffix, backend, skip, decisions = args
    from rlcache.evaluation import EvalContext
    if kind == "train":
        import run_dqn as R
        name = ("dqn:main" if variant == "dqn" else f"dqn:{variant[4:]}") + suffix
        if f"dqn|{name}|harsh|cap{CAP}|val|s{seed}" in skip:
            return kind, seed, name, []
        ctx = EvalContext.build(seed, CAP, "harsh", base_eviction=evict)
        return kind, seed, name, R.dqn_rows(ctx, variant, backend, None, decisions, suffix=suffix, splits=("val",))
    from rlcache.baselines.policies import eviction_registry, registry, s3fifo_reference_registry
    from rlcache.evaluation import evaluate
    ctx = EvalContext.build(seed, CAP, "harsh")
    specs = {s.name: s for s in registry(include_bounds=False)}
    for s in eviction_registry() + s3fifo_reference_registry():
        specs.setdefault(s.name, s)
    rows = []
    for n, sp in specs.items():
        if f"{sp.family}|{n}|harsh|cap{CAP}|val|s{seed}" not in skip:
            rows.append(evaluate(ctx, sp, "val"))
    return kind, seed, "refs", rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--procs", type=int, default=5)
    ap.add_argument("--backend", default="torch")
    ap.add_argument("--out", default="results/dqn_s3_dev.csv")
    ap.add_argument("--seeds", type=int, nargs="+", default=list(SEEDS))
    ap.add_argument("--decisions", type=int, default=None, help="SMOKE TEST ONLY")
    a = ap.parse_args()
    if min(a.seeds) < 120 and not a.decisions:
        sys.exit("Addendum M11-F uses dev seeds 120-129 only")
    out = Path(a.out)
    skip = set()
    if out.exists():
        with open(out, newline="", encoding="utf-8") as fh:
            skip = {r["run_id"] for r in csv.DictReader(fh)}
    jobs = [("train", s, v, e, sfx, a.backend, skip, a.decisions) for s in a.seeds for (v, e, sfx) in ARMS]
    jobs += [("refs", s, None, None, None, a.backend, skip, None) for s in a.seeds]
    from rlcache.results_schema import append_rows
    t0, n = time.time(), 0
    with mp.get_context("spawn").Pool(min(a.procs, len(jobs))) as pool:
        for kind, seed, name, rows in pool.imap_unordered(_job, jobs):
            n += append_rows(out, rows)
            print(f"{kind} seed {seed} {name}: +{len(rows)} rows ({time.time()-t0:.0f}s)", flush=True)
    print(f"wrote {n} new rows to {out} in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
