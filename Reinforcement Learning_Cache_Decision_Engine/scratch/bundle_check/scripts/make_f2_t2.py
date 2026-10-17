"""Regenerate T2 tables and the F2 Pareto figure from results/results.csv (one command).

    python scripts/make_f2_t2.py [--results results/results.csv] [--arm harsh]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from rlcache.analysis.report import write_reports  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--results", default="results/results.csv")
ap.add_argument("--out", default="results")
ap.add_argument("--arm", default="harsh")
ap.add_argument("--capacities", type=float, nargs="+", default=[0.01, 0.05, 0.25])
a = ap.parse_args()
for p in write_reports(a.results, a.out, a.arm, a.capacities):
    print("wrote", p)
