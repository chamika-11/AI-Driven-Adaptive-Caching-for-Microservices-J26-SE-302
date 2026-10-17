import sys, csv; sys.path.insert(0, "src")
import numpy as np
from rlcache.analysis.signal import paired_bootstrap_ci
def load(p):
    with open(p, newline="", encoding="utf-8") as fh:
        return [r for r in csv.DictReader(fh) if r["split"] == "val"]
rows = load("results/dqn_dev.csv") + load("E:/Research/New folder/results/tabq_dev.csv")
seeds = [100, 101, 102, 103, 104]
def U(p, cap):
    d = {int(r["seed"]): float(r["utility"]) for r in rows if r["policy"] == p and float(r["capacity_frac"]) == cap}
    return np.array([d[s] for s in seeds])
refs = ["place_size:p25", "fixed:redis/3600s/normal", "tabq:qbin", "tabq:bandit"]
print(f"{'cap':>5} {'agent':<13}" + "".join(f"{r:>34}" for r in refs))
for cap in (0.01, 0.05, 0.25):
    for a in ("dqn:main", "dqn:bandit", "dqn:vanilla"):
        cells = []
        for r in refs:
            d = U(a, cap) - U(r, cap)
            lo, hi = paired_bootstrap_ci(d, n_boot=4000)
            cells.append(f"{d.mean():+.4f} [{lo:+.4f},{hi:+.4f}] {int((d>0).sum())}/5")
        print(f"{cap:5.2f} {a:<13}" + "".join(f"{c:>34}" for c in cells))
