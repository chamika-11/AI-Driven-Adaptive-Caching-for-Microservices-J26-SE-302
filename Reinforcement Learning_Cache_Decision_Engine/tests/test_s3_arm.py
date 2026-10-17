"""Addendum M11-F plumbing: base_eviction on EvalContext, agent rows tagged with the eviction, S3-FIFO reference set."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


def test_eval_context_base_eviction_and_default_unchanged():
    from rlcache.config import WorkloadConfig
    from rlcache.evaluation import EvalContext
    wl = WorkloadConfig(n_requests=20_000, n_keys=300, write_interval_median_s=30_000.0)
    assert EvalContext.build(1, 0.05, "harsh", workload=wl).cfg.cache.base_eviction == "sampled_lru"
    assert EvalContext.build(1, 0.05, "harsh", workload=wl, base_eviction="s3fifo").cfg.cache.base_eviction == "s3fifo"


def test_s3fifo_reference_registry_names_and_evictions():
    from rlcache.baselines.policies import eviction_registry, s3fifo_reference_registry
    refs = s3fifo_reference_registry()
    assert len(refs) == 9 and all(s.eviction == "s3fifo" for s in refs)
    names = {s.name for s in refs}
    assert {"evict:s3fifo/redis/30s", "evict:s3fifo/both/600s", "evict:s3fifo/redis/3600s", "place_size:p25@s3fifo"} <= names
    assert {s.name for s in eviction_registry() if s.eviction == "s3fifo"} <= names   # E1 points are a subset


def test_agent_rows_are_tagged_with_the_agents_base_eviction_and_val_only():
    import run_dqn as R
    from rlcache.config import WorkloadConfig
    from rlcache.evaluation import EvalContext
    wl = WorkloadConfig(n_requests=30_000, n_keys=300, write_interval_median_s=30_000.0)
    ctx = EvalContext.build(2, 0.05, "harsh", workload=wl, base_eviction="s3fifo")
    rows = R.dqn_rows(ctx, "dqn", "numpy", None, 1_500, suffix="@s3fifo", splits=("val",))
    assert [r["split"] for r in rows] == ["val"] and rows[0]["policy"] == "dqn:main@s3fifo"
    assert "base_eviction=s3fifo" in rows[0]["notes"] and rows[0]["run_id"].startswith("dqn|dqn:main@s3fifo|")
