"""Addendum M11-E (E2) report: S1 (monotone trade-off) and S2 (frontier attempt).   python scripts/wsweep_report.py"""
import sys
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rlcache.analysis.pareto import delta_ohr, envelope  # noqa: E402
from rlcache.analysis.report import _slice, load_rows  # noqa: E402
from rlcache.analysis.signal import paired_bootstrap_ci  # noqa: E402

df = load_rows(ROOT / "results" / "results.csv")
t = _slice(df, "test", "harsh", 0.01)
W = [1.5, 2.0, 3.0, 5.0, 10.0]
name = lambda w: "dqn:main" if w == 3.0 else f"dqn:main@w{w:g}"      # noqa: E731
seeds = list(range(10))
get = lambda p, col: np.array([t[(t.policy == p) & (t.seed == s)][col].iloc[0] for s in seeds])   # noqa: E731
print("w_stale | OHR%   stale%   U      | dOHR vs envelope (all baselines incl. strong eviction) [95% CI], seeds beyond")
rows = {}
for w in W:
    p = name(w)
    ohr, st, u = get(p, "ohr"), get(p, "stale_read_rate"), get(p, "utility")
    ds, nb = [], 0
    for s in seeds:
        g = t[t.seed == s]
        me = g[g.policy == p]
        oth = g[(g.policy_class == "heuristic")]
        d, beyond = delta_ohr((float(me.stale_read_rate.iloc[0]), float(me.ohr.iloc[0])), envelope(oth.stale_read_rate.to_numpy(), oth.ohr.to_numpy()))
        ds.append(100 * d); nb += int(beyond)
    lo, hi = paired_bootstrap_ci(np.array(ds), n_boot=10_000)
    rows[w] = (ohr, st, u, np.array(ds), nb, lo, hi)
    print(f"{w:7g} | {100*ohr.mean():5.2f} {100*st.mean():7.3f} {u.mean():7.4f} | {np.mean(ds):+6.2f}pp [{lo:+.2f},{hi:+.2f}]  {nb}/10")
means = [rows[w][1].mean() for w in W]
rho = spearmanr(W, means).statistic
d = rows[10.0][1] - rows[1.5][1]
lo, hi = paired_bootstrap_ci(d, n_boot=10_000)
s1 = bool(rho <= -0.8 and hi < 0)
print(f"\nS1: Spearman(w_stale, mean stale) = {rho:+.2f}; stale(w=10) - stale(w=1.5) = {100*d.mean():+.3f}pp [{100*lo:+.3f},{100*hi:+.3f}]  -> {'SUPPORTED' if s1 else 'NOT SUPPORTED'}")
s2 = [w for w in W if rows[w][4] >= 8 and rows[w][5] > 0]
print(f"S2: weights with >= 8/10 seeds beyond the envelope and CI lower > 0: {s2 or 'none'}  -> INV-8 {'SUPPORTED at ' + str(s2) if s2 else 'NOT supported'}")
