"""R-E5 / R-E6 report on the evaluation seeds (test slice, SYNTHETIC, harsh).  POST-HOC (see PREREGISTRATION,
Addendum S1): the family and the scores were fixed after the means were already known.

    python scripts/stats_report.py [--results results/results.csv] [--out results/stats_report.json]
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from rlcache.analysis import stats as S  # noqa: E402
from rlcache.analysis.report import _slice, load_rows  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--results", default="results/results.csv")
ap.add_argument("--out", default="results/stats_report.json")
ap.add_argument("--arm", default="harsh")
a = ap.parse_args()
df = load_rows(a.results)
CAPS = (0.01, 0.05, 0.25)
AGENTS = ["dqn:main", "dqn:bandit", "dqn:vanilla", "tabq:qbin", "tabq:bandit"]
REF = "place_size:p25"
seeds = list(range(10))


def u(policy, cap):
    t = _slice(df, "test", a.arm, cap)
    d = t[t.policy == policy].set_index("seed").utility
    return np.array([d[s] for s in seeds])


out = {"family": f"{{{', '.join(AGENTS)}}} x capacities {CAPS} vs {REF}, paired dU, test slice, seeds 0-9"}
rows = []
for ag in AGENTS:
    for cap in CAPS:
        d = u(ag, cap) - u(REF, cap)
        rows.append((ag, cap, float(d.mean()), S.cohens_dz(d), S.paired_wilcoxon(d)))
adj = S.holm([r[4] for r in rows])
print(f"\n=== Paired dU vs {REF}: Wilcoxon (exact) + Holm over {len(rows)} tests, Cohen's d_z ===")
print(f"{'agent':<13}{'cap':>6}{'mean dU':>10}{'d_z':>8}{'p':>9}{'p_Holm':>9}  reject@0.05")
out["tests"] = []
for (ag, cap, m, dz, p), pa in zip(rows, adj):
    print(f"{ag:<13}{cap:6.2f}{m:+10.4f}{dz:8.2f}{p:9.4f}{pa:9.4f}  {'YES' if pa < 0.05 else 'no'}")
    out["tests"].append({"agent": ag, "cap": cap, "mean_dU": m, "dz": dz, "p": p, "p_holm": float(pa)})

print("\n=== Aggregate score = dU vs random:45, pooled over the 3 capacities (runs = seeds 0-9) ===")
score = {ag: np.column_stack([u(ag, c) - u("random:45", c) for c in CAPS]) for ag in AGENTS}
out["iqm"] = {}
for ag in AGENTS:
    p, lo, hi = S.stratified_bootstrap_ci(score[ag], n_boot=2_000)
    print(f"  IQM {ag:<13}{p:+.4f}  95% stratified-bootstrap CI [{lo:+.4f}, {hi:+.4f}]")
    out["iqm"][ag] = [p, lo, hi]
print("\n=== Probability of improvement P(row > column) on dU vs random (avg over capacities) ===")
print(f"{'':<13}" + "".join(f"{b:>13}" for b in AGENTS))
out["poi"] = {}
for x in AGENTS:
    cells = []
    for y in AGENTS:
        pr = 0.5 if x == y else S.probability_of_improvement(score[x], score[y])
        cells.append(pr)
        out["poi"][f"{x}>{y}"] = pr
    print(f"{x:<13}" + "".join(f"{c:13.2f}" for c in cells))
thr = np.linspace(-0.2, 0.1, 7)
print("\n=== Performance profile: fraction of (seed, capacity) scores above threshold ===")
print(f"{'thr':<13}" + "".join(f"{t:9.2f}" for t in thr))
for ag in AGENTS:
    print(f"{ag:<13}" + "".join(f"{v:9.2f}" for v in S.performance_profile(score[ag], thr)))
Path(a.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
