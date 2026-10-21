"""Addendum R1 report: statements T1-T3 on the real trace (Twitter cluster 52 part 000, 1% key sample), test slice, 1% capacity.

    python scripts/real_report.py [--csv results/real_cluster52.csv]
"""
import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rlcache.analysis.pareto import delta_ohr, envelope  # noqa: E402
from rlcache.analysis.signal import paired_bootstrap_ci  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--csv", default="results/real_cluster52.csv")
ap.add_argument("--out", default="results/real_cluster52_report.json")
a = ap.parse_args()
with open(a.csv, newline="", encoding="utf-8") as fh:
    rows = [r for r in csv.DictReader(fh) if "SMOKE" not in r["notes"]]
SEEDS = [0, 1, 2, 3, 4]
by = {}                                                  # (cap, split, policy) -> {seed: row}
for r in rows:
    by.setdefault((float(r["capacity_frac"]), r["split"], r["policy"]), {})[int(r["seed"])] = r
f = lambda cap, split, p, col: np.array([float(by[(cap, split, p)][s][col]) for s in SEEDS])   # noqa: E731

out = {}
for cap in (0.01, 0.05, 0.25):
    pols = [p for (c, sp, p) in by if c == cap and sp == "test" and len(by[(c, sp, p)]) == len(SEEDS)]
    ranked = sorted((p for p in pols if by[(cap, "test", p)][0]["policy_class"] != "bound" and by[(cap, "test", p)][0]["utility"] not in ("", "nan")),
                    key=lambda p: -f(cap, "test", p, "utility").mean())
    print(f"\n=== REAL trace (cluster52 part 000, 1% key sample), test slice, L2 = {cap:.0%} of footprint: top 8 by U, then agents/reference ===")
    print(f"{'policy':<34}{'U':>8}{'OHR%':>8}{'stale%':>8}")
    show = ranked[:8] + [p for p in ("dqn:main", "dqn:bandit", "dqn:main@s3fifo", "random:45", "place_size:p25") if p in pols and p not in ranked[:8]]
    for p in show:
        print(f"{p:<34}{f(cap,'test',p,'utility').mean():8.4f}{100*f(cap,'test',p,'ohr').mean():8.2f}{100*f(cap,'test',p,'stale_read_rate').mean():8.3f}")
    for bnd in ("belady_plain", "belady_ttl_constrained", "zerostale_oracle_ttl:redis"):
        if bnd in pols:
            print(f"  [bound {bnd}: OHR {100*f(cap,'test',bnd,'ohr').mean():.2f}%, stale {100*f(cap,'test',bnd,'stale_read_rate').mean():.3f}%]")

cap = 0.01
AGENTS = [p for p in ("dqn:main", "dqn:bandit", "dqn:main@s3fifo") if (cap, "test", p) in by and len(by[(cap, "test", p)]) == len(SEEDS)]
if not AGENTS:
    sys.exit("agents not finished yet")


def paired(p, q):
    d = f(cap, "test", p, "utility") - f(cap, "test", q, "utility")
    lo, hi = paired_bootstrap_ci(d, n_boot=10_000)
    return float(d.mean()), float(lo), float(hi), int((d > 0).sum())


print("\n=== Pre-registered statements (Addendum R1), test slice, 1%, paired by seed ===")
for ag in AGENTS:
    t1 = paired(ag, "random:45")
    t2a = paired(ag, "evict:s3fifo/redis/3600s")
    t2b = paired(ag, "place_size:p25")
    ok1 = t1[1] > 0 and t1[3] >= 4
    ok2a, ok2b = (t2a[1] > 0 and t2a[3] >= 4), (t2b[1] > 0 and t2b[3] >= 4)
    ds, nb = [], 0
    for s in SEEDS:
        oth = [by[(cap, "test", p)][s] for (c, sp, p) in by if c == cap and sp == "test" and s in by[(c, sp, p)]
               and by[(c, sp, p)][s]["policy_class"] == "heuristic" and not p.startswith("dqn")]
        env = envelope(np.array([float(x["stale_read_rate"]) for x in oth]), np.array([float(x["ohr"]) for x in oth]))
        me = by[(cap, "test", ag)][s]
        d, b = delta_ohr((float(me["stale_read_rate"]), float(me["ohr"])), env)
        ds.append(100 * d); nb += int(b)
    lo, hi = paired_bootstrap_ci(np.array(ds), n_boot=10_000)
    ok3 = nb >= 4 and lo > 0
    print(f"\n{ag}")
    print(f"  T1 dU vs random:45               {t1[0]:+.4f} [{t1[1]:+.4f},{t1[2]:+.4f}] {t1[3]}/5  -> {'MET' if ok1 else 'not met'}")
    print(f"  T2 dU vs evict:s3fifo/redis/3600 {t2a[0]:+.4f} [{t2a[1]:+.4f},{t2a[2]:+.4f}] {t2a[3]}/5  -> {'beats' if ok2a else 'does not beat'}")
    print(f"  T2 dU vs place_size:p25          {t2b[0]:+.4f} [{t2b[1]:+.4f},{t2b[2]:+.4f}] {t2b[3]}/5  -> {'beats' if ok2b else 'does not beat'}")
    print(f"  T3 dOHR vs envelope              {np.mean(ds):+.2f}pp [{lo:+.2f},{hi:+.2f}], beyond frontier in {nb}/5 seeds -> {'MET (INV-8 supported on this trace)' if ok3 else 'not met (INV-8 NOT supported on this trace)'}")
    out[ag] = {"T1": [t1, ok1], "T2_s3": [t2a, ok2a], "T2_size": [t2b, ok2b], "T3": [float(np.mean(ds)), float(lo), float(hi), nb, ok3]}
Path(a.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
