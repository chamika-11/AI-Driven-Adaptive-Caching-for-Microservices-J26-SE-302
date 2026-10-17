"""Amendment M9-e report: dqn_perkey vs dqn (R1, R2) and the non-gating comparisons (R3).

Dev seeds 110-119, validation slice, synthetic.  Criteria are those written in the addendum.

    python scripts/dqn_repair_report.py [--csv results/dqn_repair_dev.csv]
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from rlcache.analysis.signal import paired_bootstrap_ci  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--csv", default="results/dqn_repair_dev.csv")
ap.add_argument("--out", default="results/dqn_repair_report.json")
a = ap.parse_args()
with open(a.csv, newline="", encoding="utf-8") as fh:
    rows = [r for r in csv.DictReader(fh) if r["split"] == "val" and "SMOKE" not in r["notes"]]
seeds = list(range(110, 120))
CAPS = (0.01, 0.05, 0.25)


def U(policy, cap):
    d = {int(r["seed"]): float(r["utility"]) for r in rows
         if r["policy"] == policy and float(r["capacity_frac"]) == cap}
    return np.array([d[s] for s in seeds]) if all(s in d for s in seeds) else None


def delta(p, q, cap):
    x, y = U(p, cap), U(q, cap)
    if x is None or y is None:
        return None
    d = x - y
    lo, hi = paired_bootstrap_ci(d, n_boot=10_000)
    return float(d.mean()), float(lo), float(hi), int((d > 0).sum())


out, R1 = {}, {}
for cap in CAPS:
    print(f"\n--- L2 = {cap:.0%}: paired dU (mean [95% CI] seeds>0 of 10) ---")
    for ref in ("dqn:main", "dqn:bandit", "random:45", "place_size:p25", "fixed:redis/3600s/normal"):
        d = delta("dqn:perkey", ref, cap)
        if d is None:
            continue
        print(f"  perkey - {ref:<26}{d[0]:+.4f} [{d[1]:+.4f},{d[2]:+.4f}]  {d[3]}/10")
        out[f"perkey-{ref}@{cap}"] = d
    for p in ("dqn:main", "dqn:bandit", "dqn:perkey"):
        u = U(p, cap)
        if u is not None:
            print(f"  mean U {p:<12}{u.mean():.4f}")
d5, d25, d1 = (out.get(f"perkey-dqn:main@{c}") for c in (0.05, 0.25, 0.01))
ok = lambda d: d is not None and d[0] > 0 and d[1] > 0 and d[3] >= 7      # noqa: E731
r1_5, r1_25 = ok(d5), ok(d25)
r2 = d1 is not None and d1[1] > -0.01
verdict = ("REPAIRED" if (r1_5 and r1_25 and r2) else
           "PARTIAL" if ((r1_5 != r1_25) and r2) else "NOT REPAIRED")
print(f"\nR1@5%={r1_5}  R1@25%={r1_25}  R2@1%={r2}")
print(f"PRE-REGISTERED VERDICT (Amendment M9-e): {verdict}")
# diagnostics: share of closures dropped for lack of a same-key successor
dr = []
for r in rows:
    m = re.search(r"successor=same_key dropped_tail=(\d+) emitted=(\d+)", r["notes"])
    if m and r["split"] == "val":
        dr.append((int(m.group(1)), int(m.group(2))))
if dr:
    print(f"same_key: dropped_tail/emitted over completed epochs (diagnostic): "
          f"{sum(d for d, _ in dr)}/{sum(e for _, e in dr)}")
out["verdict"] = verdict
Path(a.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
