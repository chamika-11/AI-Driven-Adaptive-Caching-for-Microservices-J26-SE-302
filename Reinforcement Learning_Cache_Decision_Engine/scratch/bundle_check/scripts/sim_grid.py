"""Fixed-action grid on the synthetic workload: (placement x TTL) -> (OHR, stale rate, load).

    python scripts/sim_grid.py [l2_footprint_frac] [staleness_mode]

Development diagnostic for M4 (NOT an experiment result: one seed, no split, no tuning).
"""
import dataclasses
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import numpy as np  # noqa: E402

from rlcache.config import Config, StalenessConfig, TTL_BUCKETS_S, WorkloadConfig  # noqa: E402
from rlcache.sim.engine import Simulator  # noqa: E402
from rlcache.sim.policy import FixedActionPolicy, RandomPolicy  # noqa: E402
from rlcache.trace.synthetic import generate_synthetic  # noqa: E402

frac = float(sys.argv[1]) if len(sys.argv) > 1 else 0.05
mode = sys.argv[2] if len(sys.argv) > 2 else "lossy"
tr = generate_synthetic(WorkloadConfig())
cfg = Config()
cfg = dataclasses.replace(
    cfg, staleness=StalenessConfig(mode),
    cache=dataclasses.replace(cfg.cache, l2_footprint_frac=frac))
mf = int(0.1 * len(tr))
print(f"trace: {len(tr)} req, {tr.n_unique_keys()} keys, footprint {tr.footprint_bytes()/1e6:.2f} MB, "
      f"L2 = {frac:.0%} of footprint, staleness={mode}, warm-up excluded = {mf} req")
print(f"{'policy':<18}{'OHR':>7}{'stale%':>8}{'stale|hit':>10}{'backend/1k':>11}{'evict/1k':>9}{'expire/1k':>10}{'req/s':>9}")


def row(name, pol):
    t0 = time.perf_counter()
    sim = Simulator(tr, cfg, pol, seed=0, record_latencies=False, keep_closed=False)
    m = sim.run(measure_from=mf)
    dt = time.perf_counter() - t0
    sh = m.n_stale / max(m.n_hit, 1)
    print(f"{name:<18}{m.ohr():7.3f}{100*m.stale_read_rate():8.2f}{sh:10.3f}"
          f"{1000*m.backend_fetches/m.n_reads:11.1f}{1000*m.cap_evictions/m.n_reads:9.1f}"
          f"{1000*m.ttl_expirations/m.n_reads:10.1f}{len(tr)/dt:9.0f}")


for p, pn in enumerate(("local", "redis", "both")):
    for t, ttl in enumerate(TTL_BUCKETS_S):
        row(f"{pn}/{ttl}s", FixedActionPolicy.of(p, t, 1))
row("random(45)", RandomPolicy(0))
