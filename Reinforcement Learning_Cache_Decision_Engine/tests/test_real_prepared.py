"""Addendum R1 plumbing: prepared-trace save/load and data_source / run_id tagging for real traces."""
import numpy as np

from rlcache.config import WorkloadConfig
from rlcache.trace.prepared import load_prepared, save_prepared
from rlcache.trace.synthetic import generate_synthetic


def _fake_real(n=30_000):
    tr = generate_synthetic(WorkloadConfig(n_requests=n, n_keys=300, write_interval_median_s=30_000.0, seed=3))
    tr.source, tr.name = "twitter_real", "clusterXX.000_k1"
    tr.meta["key_sample_frac"] = 0.01
    return tr


def test_save_load_roundtrip(tmp_path):
    tr = _fake_real()
    save_prepared(tr, tmp_path / "t.npz", {"source_file": "x.zst"})
    back = load_prepared(tmp_path / "t.npz")
    assert back.source == "twitter_real" and back.name == tr.name and back.n_keys == tr.n_keys
    assert np.array_equal(back.ts, tr.ts) and np.array_equal(back.key, tr.key) and np.array_equal(back.op, tr.op)
    assert back.meta["key_sample_frac"] == 0.01


def test_real_trace_rows_are_tagged_and_ids_do_not_clash_with_synthetic():
    from rlcache.baselines.policies import registry
    from rlcache.evaluation import EvalContext, evaluate
    from rlcache.results_schema import validate_row
    tr = _fake_real()
    spec = {s.name: s for s in registry()}["place_size:p25"]
    real = evaluate(EvalContext.build(0, 0.05, "harsh", trace=tr), spec, "val")
    syn = evaluate(EvalContext.build(0, 0.05, "harsh", workload=WorkloadConfig(
        n_requests=30_000, n_keys=300, write_interval_median_s=30_000.0)), spec, "val")
    validate_row(real)
    assert real["data_source"] == "twitter_real" and real["trace_name"] == "clusterXX.000_k1"
    assert real["run_id"].startswith("clusterXX.000_k1|place_size|") and syn["data_source"] == "synthetic"
    assert not syn["run_id"].startswith("clusterXX") and real["run_id"] != syn["run_id"]
