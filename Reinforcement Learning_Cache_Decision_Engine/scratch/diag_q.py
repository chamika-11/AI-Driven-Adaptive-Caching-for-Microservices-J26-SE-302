import sys; sys.path.insert(0, "src")
import numpy as np
from rlcache.agents.tabular_q import train_tabular
from rlcache.actions import PLACEMENT_OF, TTL_IDX_OF
from rlcache.evaluation import EvalContext

ctx = EvalContext.build(105, 0.25, "harsh")
for label, g in (("qbin g=0.95", 0.95), ("bandit g=0", 0.0)):
    r = train_tabular(ctx, "qbin", g)
    a = r.agent
    visited = a.n_sa.sum(1) > 0
    tried = a.n_sa >= 1
    greedy = np.array([a.act_greedy(s) for s in np.flatnonzero(visited)])
    w = a.n_sa.sum(1)[visited]
    pl = np.bincount(PLACEMENT_OF[greedy], weights=w, minlength=3) / w.sum()
    print(f"\n{label}: states visited {visited.sum()}/1024, cells tried {tried.sum()}/{tried.size}, "
          f"median visits per tried cell {np.median(a.n_sa[tried]):.0f}")
    print("  Q over tried cells: min %.3f  p50 %.3f  p99 %.3f  max %.3f" % (
        a.Q[tried].min(), np.median(a.Q[tried]), np.percentile(a.Q[tried], 99), a.Q[tried].max()))
    print("  greedy placement share (visit-weighted) local/redis/both:", np.round(pl, 3))
    print("  greedy ttl idx share:", np.round(np.bincount(TTL_IDX_OF[greedy], weights=w, minlength=5) / w.sum(), 3))
    # winner's curse: how much of each state's best Q comes from a thinly-tried cell?
    best = np.array([a.act_greedy(s) for s in np.flatnonzero(visited)])
    nbest = a.n_sa[np.flatnonzero(visited), best]
    print("  visits of the chosen cell: p10 %d  p50 %d  mean %.1f ; share of states whose chosen cell has <=3 visits: %.2f" % (
        np.percentile(nbest, 10), np.median(nbest), nbest.mean(), np.mean(nbest <= 3)))
