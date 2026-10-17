"""Addendum M11-E (E1): learned agents vs the baseline envelope WITHOUT and WITH the strong-eviction baselines.

    python scripts/envelope_update.py      # test slice, seeds 0-9, harsh, synthetic
"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rlcache.analysis.pareto import delta_ohr, envelope  # noqa: E402
from rlcache.analysis.report import _slice, load_rows  # noqa: E402
from rlcache.analysis.signal import paired_bootstrap_ci  # noqa: E402

df = load_rows(ROOT / "results" / "results.csv")
AGENTS = ["dqn:main", "dqn:bandit", "dqn:vanilla", "tabq:qbin", "tabq:bandit"]
print("dOHR vs concave envelope of the other non-bound baselines (pp), paired by seed, mean [95% CI], seeds beyond frontier")
for cap in (0.01, 0.05, 0.25):
    t = _slice(df, "test", "harsh", cap)
    print(f"\n--- L2 = {cap:.0%} ---")
    for ag in AGENTS:
        cells = []
        for label, keep in (("old set", lambda r: r.family != "evict"), ("with strong eviction", lambda r: True)):
            ds, nb = [], 0
            for seed, g in t.groupby("seed"):
                me = g[g.policy == ag]
                oth = g[(g.policy_class == "heuristic") & (g.policy != ag)]
                oth = oth[oth.apply(keep, axis=1)]
                if me.empty or oth.empty:
                    continue
                d, beyond = delta_ohr((float(me.stale_read_rate.iloc[0]), float(me.ohr.iloc[0])),
                                      envelope(oth.stale_read_rate.to_numpy(), oth.ohr.to_numpy()))
                ds.append(100 * d); nb += int(beyond)
            lo, hi = paired_bootstrap_ci(np.array(ds), n_boot=10_000)
            cells.append(f"{label}: {np.mean(ds):+6.2f} [{lo:+.2f},{hi:+.2f}] beyond {nb}/10")
        print(f"  {ag:<12}" + " | ".join(cells))
    for ref in ("evict:s3fifo/redis/3600s", "evict:sieve/redis/3600s", "place_size:p25"):
        u = t[t.policy == ref].utility.mean()
        print(f"  [{ref}: mean U {u:.4f}, OHR {100*t[t.policy==ref].ohr.mean():.2f}%, stale {100*t[t.policy==ref].stale_read_rate.mean():.3f}%]")
