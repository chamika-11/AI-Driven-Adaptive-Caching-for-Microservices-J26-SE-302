import sys
sys.path.insert(0, "src")
import numpy as np
from rlcache.actions import actions_where, encode_action
from rlcache.baselines.policies import Spec
from rlcache.evaluation import EvalContext, evaluate
from rlcache.sim.policy import RandomPolicy, FixedActionPolicy

ctx = EvalContext.build(100, 0.01, "harsh")
print("L1 bytes", ctx.l1_bytes, "L2 bytes", ctx.l2_bytes, "footprint", ctx.trace.footprint_bytes(),
      "capacity_objects", ctx.capacity_objects(), "unique keys", ctx.trace.n_unique_keys())


def run(label, actions):
    spec = Spec(label, "diag", "heuristic", lambda c, a=actions: RandomPolicy(c.seed, np.asarray(a)))
    r = evaluate(ctx, spec, "test")
    print(f"{label:<42} OHR {r['ohr']:.4f}  stale {100*r['stale_read_rate']:.3f}%  U {r['utility']:.4f}"
          f"  evict/1k {r['cap_evictions_per_1k']:.0f}  expire/1k {r['ttl_expirations_per_1k']:.0f}")


run("random over all 45", np.arange(45))
run("random over TTL x placement (prio normal)", actions_where(priority=1))
run("random over TTL only (redis, normal)", actions_where(placement=1, priority=1))
run("random over priority only (redis, 3600)", actions_where(placement=1, ttl_idx=4))
run("random over placement only (3600, normal)", actions_where(ttl_idx=4, priority=1))
run("random over {5s,3600s} (redis, normal)", [encode_action(1, 0, 1), encode_action(1, 4, 1)])
run("random over {30s,3600s} (redis, normal)", [encode_action(1, 1, 1), encode_action(1, 4, 1)])
run("random over {low,high} prio (redis, 3600)", [encode_action(1, 4, 0), encode_action(1, 4, 2)])
for t in range(5):
    run(f"fixed redis ttl idx {t} normal", [encode_action(1, t, 1)])
