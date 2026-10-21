"""Addendum R2 report: within-trace T1-T3 on each real trace and the cross-trace statements X1-X3.

    python scripts/real2_report.py [--csv results/real_r2.csv]
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
ap.add_argument("--csv", default="results/real_r2.csv")
ap.add_argument("--out", default="results/real_r2_report.json")
a = ap.parse_args()
with open(a.csv, newline="", encoding="utf-8") as fh:
    rows = [r for r in csv.DictReader(fh) if "SMOKE" not in r["notes"]]
SEEDS = [0, 1, 2, 3, 4]
TR = {"c52": "cluster52.000-002_k1", "c22": "cluster22.000_k2"}
by = {}
for r in rows:
    by.setdefault((r["trace_name"], float(r["capacity_frac"]), r["split"], r["policy"]), {})[int(r["seed"])] = r


def f(t, cap, split, p, col):
    d = by[(TR[t], cap, split, p)]
    return np.array([float(d[s][col]) for s in SEEDS])


def have(t, cap, split, p):
    return (TR[t], cap, split, p) in by and len(by[(TR[t], cap, split, p)]) == len(SEEDS)


def paired(t, p, q, cap=0.01):
    d = f(t, cap, "test", p, "utility") - f(t, cap, "test", q, "utility")
    lo, hi = paired_bootstrap_ci(d, n_boot=10_000)
    return float(d.mean()), float(lo), float(hi), int((d > 0).sum())


out = {}
ARMS = ("dqn:main", "dqn:bandit", "dqn:main@s3fifo")
for t in TR:
    print(f"\n########## TRACE {t} = {TR[t]} (REAL traffic; staleness/latency modelled) ##########")
    for cap in (0.01, 0.05, 0.25):
        pols = [p for (tn, c, sp, p) in by if tn == TR[t] and c == cap and sp == "test" and len(by[(tn, c, sp, p)]) == len(SEEDS)]
        rk = sorted((p for p in pols if by[(TR[t], cap, "test", p)][0]["policy_class"] != "bound" and "@from_" not in p
                     and by[(TR[t], cap, "test", p)][0]["utility"] not in ("", "nan")), key=lambda p: -f(t, cap, "test", p, "utility").mean())
        print(f"\n--- {t}, L2 = {cap:.0%}: top 6 by U, then agents / references (test slice, 5 seeds) ---")
        print(f"{'policy':<34}{'U':>8}{'OHR%':>8}{'stale%':>8}")
        show = rk[:6] + [p for p in ARMS + ("random:45", "place_size:p25") if p in pols and p not in rk[:6]]
        for p in show:
            print(f"{p:<34}{f(t,cap,'test',p,'utility').mean():8.4f}{100*f(t,cap,'test',p,'ohr').mean():8.2f}{100*f(t,cap,'test',p,'stale_read_rate').mean():8.3f}")
        for bnd in ("belady_plain", "belady_ttl_constrained"):
            if bnd in pols:
                print(f"  [bound {bnd}: OHR {100*f(t,cap,'test',bnd,'ohr').mean():.2f}%]")
    print(f"\n=== {t}: within-trace statements T1-T3 (1%, test, paired by seed) ===")
    for ag in ARMS:
        if not have(t, 0.01, "test", ag):
            continue
        t1, t2a, t2b = paired(t, ag, "random:45"), paired(t, ag, "evict:s3fifo/redis/3600s"), paired(t, ag, "place_size:p25")
        ok = lambda x: x[1] > 0 and x[3] >= 4                                       # noqa: E731
        ds, nb = [], 0
        for s in SEEDS:
            oth = [d[s] for (tn, c, sp, p), d in by.items() if tn == TR[t] and c == 0.01 and sp == "test" and s in d
                   and d[s]["policy_class"] == "heuristic" and not p.startswith("dqn")]
            env = envelope(np.array([float(x["stale_read_rate"]) for x in oth]), np.array([float(x["ohr"]) for x in oth]))
            me = by[(TR[t], 0.01, "test", ag)][s]
            d, b = delta_ohr((float(me["stale_read_rate"]), float(me["ohr"])), env)
            ds.append(100 * d); nb += int(b)
        lo, hi = paired_bootstrap_ci(np.array(ds), n_boot=10_000)
        ok3 = nb >= 4 and lo > 0
        print(f"{ag}\n  T1 vs random:45        {t1[0]:+.4f} [{t1[1]:+.4f},{t1[2]:+.4f}] {t1[3]}/5 -> {'MET' if ok(t1) else 'not met'}"
              f"\n  T2 vs s3fifo/redis/3600 {t2a[0]:+.4f} [{t2a[1]:+.4f},{t2a[2]:+.4f}] {t2a[3]}/5 -> {'beats' if ok(t2a) else 'does not beat'}"
              f"\n  T2 vs place_size:p25    {t2b[0]:+.4f} [{t2b[1]:+.4f},{t2b[2]:+.4f}] {t2b[3]}/5 -> {'beats' if ok(t2b) else 'does not beat'}"
              f"\n  T3 dOHR vs envelope     {np.mean(ds):+.2f}pp [{lo:+.2f},{hi:+.2f}] beyond {nb}/5 -> {'MET' if ok3 else 'not met (INV-8 NOT supported)'}")
        out[f"{t}|{ag}"] = {"T1": t1, "T2_s3": t2a, "T2_size": t2b, "T3": [float(np.mean(ds)), float(lo), float(hi), nb]}

print("\n########## CROSS-TRACE (agent trained on A, evaluated on B's test slice, 1%) ##########")
for A, B in (("c52", "c22"), ("c22", "c52")):
    print(f"\n=== trained on {A}, tested on {B} ===")
    for ag in ARMS:
        x = f"{ag}@from_{A}"
        if not (have(B, 0.01, "test", x) and have(B, 0.01, "test", ag)):
            continue
        x1, x2 = paired(B, x, "random:45"), paired(B, x, "evict:s3fifo/redis/3600s")
        gap = f(B, 0.01, "test", ag, "utility") - f(B, 0.01, "test", x, "utility")
        lo, hi = paired_bootstrap_ci(gap, n_boot=10_000)
        print(f"{ag}\n  U on {B}: trained-on-{B} {f(B,0.01,'test',ag,'utility').mean():.4f} | trained-on-{A} {f(B,0.01,'test',x,'utility').mean():.4f}"
              f"\n  X1 vs random:45          {x1[0]:+.4f} [{x1[1]:+.4f},{x1[2]:+.4f}] {x1[3]}/5 -> {'MET' if (x1[1] > 0 and x1[3] >= 4) else 'not met'}"
              f"\n  X2 vs s3fifo/redis/3600  {x2[0]:+.4f} [{x2[1]:+.4f},{x2[2]:+.4f}] {x2[3]}/5 -> {'beats' if (x2[1] > 0 and x2[3] >= 4) else 'does not beat'}"
              f"\n  X3 transfer gap (own - transferred) {gap.mean():+.4f} [{lo:+.4f},{hi:+.4f}]")
        out[f"{A}->{B}|{ag}"] = {"X1": x1, "X2": x2, "X3": [float(gap.mean()), float(lo), float(hi)]}
Path(a.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
