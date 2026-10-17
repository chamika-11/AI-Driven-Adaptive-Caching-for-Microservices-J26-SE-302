"""Summarise the evaluation-seed DQN run (and tabular Q for context) on the TEST slice.

Pre-registered statistics (Addendum M6-4 / M9): ΔOHR versus the concave envelope of the other
non-bound policies, paired by seed, plus ΔU / ΔOHR / Δstale versus fixed reference rules and a
two-axis dominance count (C-49).  SYNTHETIC workload only.

    python scripts/dqn_eval_summary.py [--results results/results.csv] [--out results/dqn_eval_summary.json]
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from rlcache.analysis.report import _slice, learned_vs_baselines, load_rows  # noqa: E402
from rlcache.analysis.signal import paired_bootstrap_ci  # noqa: E402

LEARNED = ["dqn:main", "dqn:bandit", "dqn:vanilla", "tabq:qbin", "tabq:bandit"]
REFS = ["random:45", "place_size:p25", "fixed:redis/3600s/normal"]

ap = argparse.ArgumentParser()
ap.add_argument("--results", default="results/results.csv")
ap.add_argument("--out", default="results/dqn_eval_summary.json")
ap.add_argument("--arm", default="harsh")
a = ap.parse_args()
df = load_rows(a.results)
summary = {}
for cap in (0.01, 0.05, 0.25):
    t = _slice(df, "test", a.arm, cap)
    print(f"\n=== L2 = {cap:.0%} of footprint, TEST slice, seeds 0-9, synthetic, harsh ===")
    print(f"{'policy':<14}{'U':>8}{'OHR%':>8}{'stale%':>8}  {'dOHR vs envelope [95% CI]':<34}{'beyond':>7}")
    for p in LEARNED:
        g = t[t.policy == p]
        if g.empty:
            continue
        r = learned_vs_baselines(df, p, a.arm, cap)
        lo, hi = r["delta_ohr_ci"]
        print(f"{p:<14}{g.utility.mean():8.4f}{100*g.ohr.mean():8.2f}{100*g.stale_read_rate.mean():8.3f}  "
              f"{100*r['delta_ohr_mean']:+7.3f}pp [{100*lo:+.3f},{100*hi:+.3f}]{'':<6}{r['n_beyond_frontier']:>3}/10")
        entry = {"U": float(g.utility.mean()), "ohr": float(g.ohr.mean()),
                 "stale": float(g.stale_read_rate.mean()), "n_seeds": int(len(g)), **{
                     k: v for k, v in r.items() if k.startswith(("delta", "n_"))}}
        for ref in REFS:
            m = g.set_index("seed")
            q = t[t.policy == ref].set_index("seed")
            c = m.index.intersection(q.index)
            dU = (m.loc[c, "utility"] - q.loc[c, "utility"]).to_numpy()
            dO = (m.loc[c, "ohr"] - q.loc[c, "ohr"]).to_numpy()
            dS = (m.loc[c, "stale_read_rate"] - q.loc[c, "stale_read_rate"]).to_numpy()
            lo2, hi2 = paired_bootstrap_ci(dU, n_boot=10_000)
            dom = int(((dO >= 0) & (dS <= 0) & ((dO > 0) | (dS < 0))).sum())
            entry[f"vs_{ref}"] = {"dU": [float(dU.mean()), lo2, hi2, int((dU > 0).sum())],
                                  "dOHR": float(dO.mean()), "dStale": float(dS.mean()),
                                  "seeds_dominating": dom}
            print(f"   vs {ref:<26} dU {dU.mean():+.4f} [{lo2:+.4f},{hi2:+.4f}] {int((dU>0).sum())}/10 | "
                  f"dOHR {100*dO.mean():+.2f}pp dstale {100*dS.mean():+.3f}pp | dominates in {dom}/10 seeds")
        summary[f"{p}@{cap}"] = entry
Path(a.out).write_text(json.dumps(summary, indent=1), encoding="utf-8")
print("\nwrote", a.out)
