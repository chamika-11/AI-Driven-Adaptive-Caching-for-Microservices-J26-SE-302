import sys
from pathlib import Path
sys.path.insert(0, "src"); sys.path.insert(0, "scripts")
import numpy as np
import placement_signal as ps
from rlcache.actions import encode_action
from rlcache.reward import compute_reward
from rlcache.runner import make_run
from rlcache.sim.engine import R_TRUNC
from rlcache.sim.policy import RandomPolicy
from rlcache.features_spec import FEATURE_INDEX

UTIL = FEATURE_INDEX["utilisation"]
r = ps.Regime("harsh", frac=0.25, ratio=0.10, p_inv=0.2, d_inv=10.0, p_bypass=0.3)
tr = ps.get_trace(100, r.alpha, r.n_requests, r.n_keys)
cfg = ps.make_cfg(r)
for label, sel in (("redis/3600", lambda o, c: encode_action(1, 4, 1)),
                   ("random45", (lambda p: (lambda o, c: p.decide(c)))(RandomPolicy(1)))):
    run = make_run(tr, cfg, sel, keep_closed=True, seed=0)
    run.go()
    cap = run.sim.l1.cap + run.sim.l2.cap
    P = [compute_reward(i, cfg.reward, cap, float(i.payload[0][UTIL]))
         for i in run.sim.closed if i.close_reason != R_TRUNC]
    names = ("hit", "lat", "stale", "backend", "mem", "stampede")
    A = np.array([[getattr(p, n) for n in names] for p in P])
    raw = np.array([p.raw for p in P])
    print(f"\n{label}: {len(P)} decisions")
    print("  mean of each term :", {n: round(float(A[:, j].mean()), 4) for j, n in enumerate(names)})
    print("  mean |term| share :", {n: round(float(np.abs(A[:, j]).mean() / np.abs(A).mean(0).sum()), 3)
                                    for j, n in enumerate(names)})
    print("  gate<1 fraction   :", round(float(np.mean([p.gate < 1 for p in P])), 4))
    print("  |raw|>10 %:", round(100 * float(np.mean(np.abs(raw) > 10)), 2),
          " |raw|>1000 % (clips under /100):", round(100 * float(np.mean(np.abs(raw) > 1000)), 3),
          " p50/p90/p99 of raw/100:", np.round(np.percentile(raw / 100, [50, 90, 99]), 3))
    s = raw.sum()
    top = np.sort(raw)[::-1]
    print("  share of total reward from top 1% of decisions:", round(float(top[:max(1, len(top)//100)].sum() / s), 3))
