"""Live replay of the trained model (and baselines) in the simulator; metrics for Grafana at http://localhost:<port>/metrics

    # synthetic world (works with the saved checkpoints):
    python scripts/live_dashboard.py --trace synthetic --seed 0 --cap 0.01 --model results/dqn_ckpt/dqn_cap0.01_s0.npz --speed 60 --loop
    # real Twitter trace sample (needs a model trained on it: scripts/train_live_checkpoint.py):
    python scripts/live_dashboard.py --trace real --prepared data/processed/cluster52_000_k1.npz --cap 0.01 \
        --model results/dqn_ckpt/real_cluster52.000_k1_dqn_cap0.01_s0.npz --speed 20 --loop

After retraining on more parts (0001, 0002 ...) point --prepared and --model at the new files; nothing else changes.
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rlcache.baselines.policies import eviction_registry, registry, s3fifo_reference_registry  # noqa: E402
from rlcache.evaluation import EvalContext  # noqa: E402
from rlcache.live.metrics import MetricStore, serve  # noqa: E402
from rlcache.live.runner import LiveRunner, load_agent  # noqa: E402
from rlcache.trace.prepared import load_prepared  # noqa: E402

DEFAULT_RIVALS = ("random:45", "place_size:p25", "evict:s3fifo/redis/3600s", "evict:s3fifo/both/3600s")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", choices=("synthetic", "real"), default="synthetic")
    ap.add_argument("--prepared", default="data/processed/cluster52_000_k1.npz")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--cap", type=float, default=0.01)
    ap.add_argument("--model", required=True, help="checkpoint .npz (numpy-loadable) of the trained model")
    ap.add_argument("--model-eviction", default="sampled_lru", help="base eviction the model was trained with")
    ap.add_argument("--rivals", nargs="*", default=list(DEFAULT_RIVALS))
    ap.add_argument("--speed", type=float, default=60.0, help="simulated seconds per real second")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--loop", action="store_true", help="restart the replay when it ends")
    a = ap.parse_args()

    if a.trace == "real":
        ctx = EvalContext.build(a.seed, a.cap, "harsh", trace=load_prepared(ROOT / a.prepared))
    else:
        ctx = EvalContext.build(a.seed, a.cap, "harsh")
    store = MetricStore()
    store.describe("rlcache_window_hit_ratio", "hit ratio over the last ~10 s of wall time")
    store.describe("rlcache_window_stale_rate", "stale reads / reads over the last ~10 s of wall time")
    store.describe("rlcache_window_utility", "selection utility U over the last ~10 s of wall time")
    store.describe("rlcache_action_total", "decisions by placement / ttl / priority")
    store.set("rlcache_info", 1, trace=ctx.trace_name, data_source=ctx.trace.source, capacity=a.cap, model=Path(a.model).name,
              speed=a.speed)
    specs = {s.name: s for s in registry()}
    for s in eviction_registry() + s3fifo_reference_registry():
        specs.setdefault(s.name, s)

    make_agent, meta = load_agent(str(ROOT / a.model) if not Path(a.model).is_absolute() else a.model, ctx)
    runners = [LiveRunner("agent (RL model)", ctx, make_agent, store, speed=a.speed, eviction=a.model_eviction, loop=a.loop, agent=True)]
    for n in a.rivals:
        sp = specs[n]
        runners.append(LiveRunner(n, ctx, (lambda sp=sp: sp.make(ctx)), store, speed=a.speed, eviction=sp.eviction, loop=a.loop))
    srv = serve(store, a.port)
    for r in runners:
        r.start()
    t0 = ctx.slice_for("test")
    print(f"serving metrics on http://localhost:{a.port}/metrics | trace {ctx.trace_name} ({ctx.trace.source}) | model {Path(a.model).name} "
          f"(trained decisions {meta.get('decisions')}) | speed x{a.speed:g} | replay length {(ctx.trace.ts[t0[1]-1]-ctx.trace.ts[t0[0]]):.0f} simulated s "
          f"= {(ctx.trace.ts[t0[1]-1]-ctx.trace.ts[t0[0]])/a.speed:.0f} s real", flush=True)
    try:
        while any(not r.done for r in runners):
            time.sleep(1.0)
            for r in runners:
                if r.error is not None:
                    print("ERROR in", r.name, repr(r.error), flush=True)
                    raise SystemExit(1)
        print("replay finished (use --loop to repeat); metrics stay available for 30 s", flush=True)
        time.sleep(30)
    except KeyboardInterrupt:
        pass
    for r in runners:
        r.stop_event.set()
    srv.shutdown()


if __name__ == "__main__":
    main()
