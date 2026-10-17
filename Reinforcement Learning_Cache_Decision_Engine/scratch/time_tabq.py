import sys, time
sys.path.insert(0, "src")
from rlcache.agents.tabular_q import train_tabular
from rlcache.evaluation import EvalContext
for cap in (0.01, 0.25):
    t0 = time.time()
    ctx = EvalContext.build(100, cap, "harsh")
    t1 = time.time()
    r = train_tabular(ctx, "qbin")
    t2 = time.time()
    print(f"cap {cap}: build {t1-t0:.1f}s train {t2-t1:.1f}s  decisions {r.decisions} epochs {r.epochs} "
          f"coverage {r.agent.coverage():.3f} mean|TD| {r.td_abs_mean:.4f} "
          f"actions used {(r.action_hist>0).sum()} edges0 {[round(float(x),4) for x in r.disc.edges[0]]}")
