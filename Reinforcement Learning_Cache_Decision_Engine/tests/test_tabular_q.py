"""M8: tabular Q mechanics, discretiser, training/evaluation plumbing."""
import dataclasses

import numpy as np
import pytest

from rlcache.agents.tabular_q import (Discretizer, GreedyTabularPolicy, TabularQ, eps_at,
                                      train_tabular)
from rlcache.baselines.policies import Spec
from rlcache.config import N_ACTIONS, TabularQConfig, WorkloadConfig
from rlcache.evaluation import EvalContext, evaluate_sim_policy
from rlcache.features_spec import FEATURE_INDEX, TABULAR_FEATURE_IDX
from rlcache.results_schema import validate_row

WL = WorkloadConfig(n_requests=30_000, n_keys=300, write_interval_median_s=30_000.0)
SMALL = TabularQConfig(total_decisions=6_000, calib_requests=3_000)


# ---- the update rule, hand-computed ---------------------------------------------------------------
def test_bellman_update_hand_computed():
    q = TabularQ(4, alpha=0.5, gamma=0.9)
    q.Q[2] = [0.0, 1.0] + [0.0] * (N_ACTIONS - 2)
    td = q.update(s=0, a=3, r=2.0, s2=2)
    assert td == pytest.approx(2.0 + 0.9 * 1.0 - 0.0)
    assert q.Q[0, 3] == pytest.approx(0.5 * 2.9)
    q.update(0, 3, 2.0, 2)
    assert q.Q[0, 3] == pytest.approx(1.45 + 0.5 * (2.9 - 1.45))
    assert q.n_sa[0, 3] == 2 and q.n_updates == 2


@pytest.mark.parametrize("gamma", [0.0, 0.9])
def test_gamma_controls_value_propagation(gamma):
    """s0 -(r=0)-> s1 -(r=1)-> s2.  Q(s1) -> 1 always; Q(s0) -> gamma * 1 (0 for a bandit)."""
    q = TabularQ(3, alpha=0.5, gamma=gamma)
    for _ in range(200):
        q.update(1, 0, 1.0, 2)
        q.update(0, 0, 0.0, 1)
    assert q.Q[1, 0] == pytest.approx(1.0, abs=1e-6)
    assert q.Q[0, 0] == pytest.approx(gamma, abs=1e-6)


def test_greedy_only_considers_tried_actions_and_falls_back():
    q = TabularQ(2, alpha=0.5, gamma=0.9)
    q.default_action = 11
    assert q.act_greedy(0) == 11                                   # never visited -> fallback
    q.update(0, 5, -0.01, 0)                                       # only action 5 tried, Q < 0
    assert q.Q[0].max() == 0.0 and q.act_train(0) != 5             # training argmax picks an untried 0
    assert q.act_greedy(0) == 5                                    # greedy: tried actions only
    q.update(0, 9, 0.2, 0)
    assert q.act_greedy(0) == 9
    q.n_sa[:] = 0
    assert q.act_greedy(0) == 11


def test_finalize_picks_a_visited_action():
    q = TabularQ(3, 0.5, 0.0)
    for s in range(3):
        for _ in range(5):
            q.update(s, 7, 1.0, s)
        q.update(s, 3, 5.0, s)
    q.finalize()
    assert q.n_sa[:, q.default_action].sum() > 0


def test_epsilon_schedule_matches_the_spec():
    cfg = TabularQConfig()
    total = 100_000
    assert eps_at(0, total, cfg) == 1.0
    assert eps_at(15_000, total, cfg) == pytest.approx(0.55)
    assert eps_at(30_000, total, cfg) == pytest.approx(0.10)
    assert eps_at(99_000, total, cfg) == pytest.approx(0.10)


# ---- discretiser --------------------------------------------------------------------------------------
def test_qbin_is_equal_frequency_and_ewidth_collapses_for_small_features():
    rng = np.random.default_rng(0)
    obs = np.zeros((20_000, 19))
    for f in TABULAR_FEATURE_IDX:
        obs[:, f] = rng.exponential(0.02, 20_000).clip(0, 1)        # skewed, mostly tiny
    q = Discretizer("qbin").fit(obs)
    idx = q.index_many(obs)
    assert idx.min() >= 0 and idx.max() < 1024
    for pos in range(5):                                            # each feature: ~25% per bin
        b = (idx // 4 ** (4 - pos)) % 4
        assert np.allclose(np.bincount(b, minlength=4) / len(b), 0.25, atol=0.02)
    e = Discretizer("ewidth").fit(obs)
    assert len(np.unique(e.index_many(obs))) < len(np.unique(idx)) / 4   # MD-literal bins collapse
    assert q.index(obs[5]) == int(q.index_many(obs[5:6])[0])


def test_state_index_uses_the_five_pre_registered_features_in_order():
    d = Discretizer("ewidth")
    names = {n for n, i in FEATURE_INDEX.items() if i in TABULAR_FEATURE_IDX}
    assert names == {"utilisation", "hit_ratio", "count_1000", "volatility", "predicted_ttl"}
    o = np.zeros(19)
    base = d.index(o)
    for pos, f in enumerate(TABULAR_FEATURE_IDX):
        o2 = o.copy()
        o2[f] = 0.99                                                # top bin of exactly that feature
        assert d.index(o2) - base == 3 * 4 ** (4 - pos)


# ---- training and evaluation plumbing ----------------------------------------------------------------------
@pytest.fixture(scope="module")
def ctx():
    return EvalContext.build(3, 0.05, "harsh", workload=WL)


def test_training_is_deterministic_and_respects_the_budget(ctx):
    a = train_tabular(ctx, "qbin", cfg=SMALL)
    b = train_tabular(ctx, "qbin", cfg=SMALL)
    assert a.decisions == 6_000 and a.agent.n_updates > 1_000
    assert np.array_equal(a.agent.Q, b.agent.Q) and np.array_equal(a.disc.edges[0], b.disc.edges[0])
    assert a.norm.frozen and a.epochs >= 1
    assert a.action_hist.sum() == 6_000 and (a.action_hist > 0).sum() > 20     # explored widely


def test_training_uses_only_the_training_slice(ctx):
    """Scrambling the validation/test part of the trace cannot change the learned table."""
    rng = np.random.default_rng(0)
    key = ctx.trace.key.copy()
    key[ctx.splits.train_end:] = rng.integers(0, ctx.trace.n_keys, len(key) - ctx.splits.train_end)
    ctx2 = EvalContext.build(3, 0.05, "harsh", trace=dataclasses.replace(ctx.trace, key=key))
    # Capacity is a design parameter derived from the WHOLE trace's footprint (M6-2); scrambling
    # keys changes that footprint, so hold the cache size fixed to isolate what training sees.
    ctx2.l1_bytes, ctx2.l2_bytes = ctx.l1_bytes, ctx.l2_bytes
    a = train_tabular(ctx, "qbin", cfg=SMALL)
    b = train_tabular(ctx2, "qbin", cfg=SMALL)
    assert np.array_equal(a.agent.Q, b.agent.Q)


def test_greedy_evaluation_row_is_valid_and_does_not_learn(ctx):
    res = train_tabular(ctx, "qbin", cfg=SMALL)
    q_before = res.agent.Q.copy()
    pol = GreedyTabularPolicy(res, ctx)
    spec = Spec("tabq:qbin", "tabular_q", "learned", lambda c: pol)
    row = evaluate_sim_policy(ctx, spec, "val", policy=pol)
    validate_row(row)
    assert row["policy_class"] == "learned" and row["n_reads"] > 0
    assert np.array_equal(res.agent.Q, q_before)
    assert 0.0 <= pol.unvisited_decision_share() <= 1.0
    assert pol.action_hist.sum() > 0


def test_bandit_variant_has_gamma_zero(ctx):
    res = train_tabular(ctx, "qbin", gamma=0.0, cfg=SMALL)
    assert res.gamma == 0.0 and res.agent.gamma == 0.0


def test_learned_rows_flow_into_t2_frontier_and_paired_statistic(tmp_path):
    from rlcache.agents.tabular_q import GreedyTabularPolicy
    from rlcache.analysis import report as R
    from rlcache.baselines.policies import registry
    from rlcache.evaluation import evaluate
    from rlcache.results_schema import append_rows

    wl = WorkloadConfig(n_requests=12_000, n_keys=200, write_interval_median_s=30_000.0)
    path = tmp_path / "r.csv"
    keep = {"fixed", "random", "place_size"}
    for seed in (0, 1, 2):
        c = EvalContext.build(seed, 0.05, "harsh", workload=wl)
        rows = [evaluate(c, s, sp) for s in registry(include_bounds=False) if s.family in keep
                for sp in ("val", "test")]
        res = train_tabular(c, "qbin", cfg=TabularQConfig(total_decisions=3_000, calib_requests=2_000))
        for sp in ("val", "test"):
            pol = GreedyTabularPolicy(res, c)
            rows.append(evaluate_sim_policy(c, Spec("tabq:qbin", "tabular_q", "learned", lambda x, p=pol: p),
                                            sp, policy=pol))
        append_rows(path, rows)
    df = R.load_rows(path)
    t = R.t2_table(df, "harsh", 0.05)
    assert "tabq:qbin" in set(t.policy) and (t[t.policy == "tabq:qbin"]["class"] == "learned").all()
    fs = R.frontier_summary(df, "harsh", 0.05)
    assert not any(r["policy"] == "tabq:qbin" for r in fs["non_dominated"])     # agents never form the frontier
    lb = R.learned_vs_baselines(df, "tabq:qbin", "harsh", 0.05, n_boot=500)
    assert lb["n_seeds"] == 3 and "d_utility_vs_random:45" in lb
    assert lb["n_above_envelope"] + (3 - lb["n_above_envelope"]) == 3
    assert R.write_reports(path, tmp_path / "out", "harsh", [0.05])
