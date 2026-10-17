"""Addendum M11-F report: criteria D1 / D2 / D3 for the agent on S3-FIFO base eviction (dev seeds 120-129, validation slice).

    python scripts/s3_dev_report.py [--csv results/dqn_s3_dev.csv]
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rlcache.analysis.pareto import delta_ohr, envelope  # noqa: E402
from rlcache.analysis.signal import paired_bootstrap_ci  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--csv", default="results/dqn_s3_dev.csv")
ap.add_argument("--out", default="results/dqn_s3_dev_report.json")
a = ap.parse_args()
with open(a.csv, newline="", encoding="utf-8") as fh:
    rows = [r for r in csv.DictReader(fh) if r["split"] == "val" and "SMOKE" not in r["notes"]]
SEEDS = list(range(120, 130))
by = {}
for r in rows:
    by.setdefault(r["policy"], {})[int(r["seed"])] = r
AGENT, ABL, OLD = "dqn:main@s3fifo", "dqn:bandit@s3fifo", "dqn:main"
need = [AGENT, "evict:s3fifo/redis/3600s"]
for p in need:
    if p not in by or any(s not in by[p] for s in SEEDS):
        sys.exit(f"incomplete data for {p}")
f = lambda p, col: np.array([float(by[p][s][col]) for s in SEEDS])          # noqa: E731


def paired(p, q, col="utility"):
    d = f(p, col) - f(q, col)
    lo, hi = paired_bootstrap_ci(d, n_boot=10_000)
    return float(d.mean()), float(lo), float(hi), int((d > 0).sum())


out = {}
print("mean validation slice, dev seeds 120-129, 1% capacity (synthetic):")
print(f"{'policy':<28}{'U':>8}{'OHR%':>8}{'stale%':>8}")
for p in [AGENT, ABL, OLD, "evict:s3fifo/redis/3600s", "evict:s3fifo/both/3600s", "place_size:p25@s3fifo", "place_size:p25"]:
    if p in by and all(s in by[p] for s in SEEDS):
        print(f"{p:<28}{f(p,'utility').mean():8.4f}{100*f(p,'ohr').mean():8.2f}{100*f(p,'stale_read_rate').mean():8.3f}")

d1 = paired(AGENT, "evict:s3fifo/redis/3600s")
d1ok = d1[0] > 0 and d1[1] > 0 and d1[3] >= 8
print(f"\nD1 dU(agent - evict:s3fifo/redis/3600s) = {d1[0]:+.4f} [{d1[1]:+.4f},{d1[2]:+.4f}]  {d1[3]}/10 seeds  -> {'MET' if d1ok else 'not met'}")
out["D1"] = {"dU": d1, "met": bool(d1ok)}

# D2: beyond the envelope of ALL non-learned, non-bound references
beyond, ds = 0, []
for s in SEEDS:
    me = by[AGENT][s]
    oth = [r[s] for p, r in by.items() if s in r and r[s]["policy_class"] == "heuristic" and not p.startswith("dqn")]
    env = envelope(np.array([float(x["stale_read_rate"]) for x in oth]), np.array([float(x["ohr"]) for x in oth]))
    d, b = delta_ohr((float(me["stale_read_rate"]), float(me["ohr"])), env)
    ds.append(100 * d)
    beyond += int(b)
lo, hi = paired_bootstrap_ci(np.array(ds), n_boot=10_000)
d2ok = beyond >= 8 and lo > 0
print(f"D2 dOHR vs envelope of all {len(oth)} non-learned references = {np.mean(ds):+.2f}pp [{lo:+.2f},{hi:+.2f}], beyond the frontier in {beyond}/10 seeds -> {'MET' if d2ok else 'not met'}")
out["D2"] = {"dOHR_pp": [float(np.mean(ds)), float(lo), float(hi)], "beyond": beyond, "met": bool(d2ok)}

# D3: best S3-FIFO reference chosen on these same seeds (generous to the reference)
s3 = [p for p in by if "s3fifo" in p and not p.startswith("dqn") and all(s in by[p] for s in SEEDS)]
best = max(s3, key=lambda p: f(p, "utility").mean())
d3 = paired(AGENT, best)
print(f"D3 dU(agent - best S3-FIFO reference by mean U = {best}) = {d3[0]:+.4f} [{d3[1]:+.4f},{d3[2]:+.4f}]  {d3[3]}/10  (strict check, not gating)")
out["D3"] = {"best_ref": best, "dU": d3}

verdict = "SUPPORTED-FRONTIER" if (d1ok and d2ok) else "SUPPORTED-U" if d1ok else "NOT SUPPORTED"
print(f"\nPRE-REGISTERED VERDICT (Amendment M11-F): {verdict}")
out["verdict"] = verdict

print("\nnon-gating:")
for q, lab in ((OLD, "agent on S3-FIFO minus agent on sampled-LRU (eviction effect)"), ("place_size:p25@s3fifo", "agent minus place_size rule under S3-FIFO")):
    if q in by and all(s in by[q] for s in SEEDS):
        d = paired(AGENT, q)
        print(f"  {lab}: {d[0]:+.4f} [{d[1]:+.4f},{d[2]:+.4f}] {d[3]}/10")
        out[lab] = d
if ABL in by and all(s in by[ABL] for s in SEEDS):
    d = paired(ABL, "evict:s3fifo/redis/3600s")
    print(f"  ablation bandit - evict:s3fifo/redis/3600s: {d[0]:+.4f} [{d[1]:+.4f},{d[2]:+.4f}] {d[3]}/10")
    out["ablation_bandit_vs_ref"] = d
print("  agent action shares (mean): local %.2f redis %.2f both %.2f; median TTL (s) of chosen actions: %.0f" % (
    f(AGENT, "share_local").mean(), f(AGENT, "share_redis").mean(), f(AGENT, "share_both").mean(), np.median(f(AGENT, "ttl_median_s"))))
Path(a.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
