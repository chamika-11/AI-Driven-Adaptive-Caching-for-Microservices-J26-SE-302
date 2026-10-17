"""M0 gate: config loads (defaults == default.yaml), validation, feature table, results schema."""
from pathlib import Path

import pytest

from rlcache import config as C
from rlcache import features_spec as F
from rlcache import results_schema as R

ROOT = Path(__file__).resolve().parents[1]


def test_default_yaml_matches_builtin_defaults():
    from_yaml = C.load_config(ROOT / "configs" / "default.yaml")
    assert from_yaml == C.Config()
    assert from_yaml.digest() == C.Config().digest()


def test_invariants_are_constants():
    assert C.N_FEATURES == 19 and C.N_ACTIONS == 45
    assert C.HARD_CAP_S == 7200
    assert C.PLACEMENTS == ("local", "redis", "both")
    assert C.PRIORITY_LEVELS == ("low", "normal", "high")


def test_reward_weights_match_spec_and_enforce_ordering():
    w = C.RewardWeights()
    assert (w.w_hit, w.w_lat, w.w_stale, w.w_backend, w.w_mem, w.w_stampede) == (
        1.0, 0.5, 3.0, 1.0, 0.3, 2.0)
    assert w.stampede_norm == 2.4 and w.clip == 10.0
    with pytest.raises(ValueError):
        C.RewardWeights(w_hit=1.0, w_stale=0.5)          # w_stale must exceed w_hit


def test_staleness_config_validation():
    assert C.StalenessConfig().mode == "lossy"
    for bad in (dict(mode="nope"), dict(p_inv_l1=1.5), dict(p_bypass=-0.1), dict(d_inv_l1_s=-1)):
        with pytest.raises(ValueError):
            C.StalenessConfig(**bad)


def test_split_validation_and_defaults():
    s = C.SplitConfig()
    assert (s.predictor_fit_end, s.train_end, s.val_end) == (0.30, 0.70, 0.80)
    with pytest.raises(ValueError):
        C.SplitConfig(predictor_fit_end=0.5, train_end=0.4)


def test_dqn_defaults_match_spec_table():
    d = C.DQNConfig()
    assert (d.hidden, d.lr, d.gamma, d.batch_size, d.buffer_size) == (128, 2.5e-4, 0.95, 128, 200_000)
    assert (d.learning_starts, d.train_every, d.tau, d.max_grad_norm) == (10_000, 4, 0.005, 10.0)
    assert (d.eps_start, d.eps_end, d.eps_decay_frac, d.total_decisions) == (1.0, 0.10, 0.30, 300_000)
    assert d.n_step == 1                                  # D-12


def test_cache_capacity_ratio():
    c = C.CacheConfig()
    assert c.l1_capacity_bytes == int(c.l2_capacity_bytes * 0.10)
    assert c.priority_mult == (0.5, 1.0, 2.0)


def test_unknown_keys_rejected():
    with pytest.raises(KeyError):
        C.config_from_dict({"reward": {"w_nonexistent": 1}})
    with pytest.raises(KeyError):
        C.config_from_dict({"bogus_section": {}})


def test_workload_defaults_span_hours():
    w = C.WorkloadConfig()
    assert w.duration_s >= 6 * 3600                       # D-15
    assert w.locality_prob == 0.3


# ---- feature table -----------------------------------------------------------------------
def test_exactly_19_features_in_three_blocks():
    assert len(F.FEATURES) == 19 and len(F.FEATURE_NAMES) == 19
    assert len(set(F.FEATURE_NAMES)) == 19
    blocks = [f.block for f in F.FEATURES]
    assert blocks.count(F.BLOCK_KEY) == 10
    assert blocks.count(F.BLOCK_CACHE) == 8
    assert blocks.count(F.BLOCK_PRED) == 1
    assert [f.index for f in F.FEATURES] == list(range(19))


def test_no_miss_ratio_and_no_key_identity_features():
    names = set(F.FEATURE_NAMES)
    assert "hit_ratio" in names
    assert not any("miss" in n for n in names)            # INV-1: hit ratio only
    assert not any(n in ("key", "key_id") for n in names)
    assert not any("step" in n or "episode" in n for n in names)   # C-1: no episode position


def test_tabular_feature_indices_fix_prototype_bug():
    """C-21: the prototype's FEAT_IDX=[10,11,4,0,8] used 0 (log recency) for volatility."""
    assert F.TABULAR_FEATURE_IDX == (10, 11, 4, 9, 8)
    assert F.FEATURE_NAMES[9] == "volatility" and F.FEATURE_NAMES[0] == "log_recency_1"
    assert [F.FEATURE_NAMES[i] for i in F.TABULAR_FEATURE_IDX] == list(F.TABULAR_FEATURES)


def test_state_ladder_is_strictly_nested():
    order = ["S0", "S1", "S2", "S3", "S4", "S5"]
    for a, b in zip(order, order[1:]):
        assert set(F.STATE_LADDER[a]) < set(F.STATE_LADDER[b])
    assert set(F.STATE_LADDER["S5"]) == set(F.FEATURE_NAMES)
    for names in F.STATE_LADDER.values():
        assert all(n in F.FEATURE_INDEX for n in names)


# ---- results schema ----------------------------------------------------------------------
def _row(**kw):
    base = dict(run_id="r0", data_source="synthetic", trace_name="syn0", split="test",
                policy="fixed_ttl_30", policy_class="heuristic", seed=0,
                n_reads=100, n_fresh=60, n_stale=10, n_miss=30,
                ohr=0.7, stale_read_rate=0.1)
    base.update(kw)
    return base


def test_results_round_trip(tmp_path):
    p = tmp_path / "results.csv"
    assert R.append_rows(p, [_row(), _row(run_id="r1", seed=1)]) == 2
    assert R.append_rows(p, [_row(run_id="r2")]) == 1      # append keeps one header
    rows = R.read_rows(p)
    assert [r["run_id"] for r in rows] == ["r0", "r1", "r2"]
    assert rows[0]["data_source"] == "synthetic"
    assert tuple(rows[0]) == R.COLUMN_NAMES


def test_results_rejects_bad_rows(tmp_path):
    p = tmp_path / "r.csv"
    with pytest.raises(ValueError):
        R.append_rows(p, [_row(n_fresh=50)])               # 50+10+30 != 100
    with pytest.raises(ValueError):
        R.append_rows(p, [_row(ohr=1.5)])
    with pytest.raises(ValueError):
        R.append_rows(p, [_row(data_source="twitter")])    # must be synthetic | twitter_real
    with pytest.raises(KeyError):
        R.append_rows(p, [_row(cumulative_reward=3.0)])    # no ad-hoc columns
    with pytest.raises(ValueError):
        R.append_rows(p, [_row(split="all")])


def test_results_has_no_comparable_reward_column():
    assert "cumulative_reward" not in R.COLUMN_NAMES
    assert "train_return" in R.COLUMN_NAMES                # diagnostics only
