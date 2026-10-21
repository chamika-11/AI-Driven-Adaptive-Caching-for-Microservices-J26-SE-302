"""M7 machinery: bootstrap, criteria logic (G1-G4), acc=1.0 equivalence, regression alignment."""
import numpy as np
import pytest

from rlcache.analysis import signal as S
from rlcache.baselines.policies import registry
from rlcache.config import WorkloadConfig
from rlcache.evaluation import EvalContext, evaluate

WL = WorkloadConfig(n_requests=20_000, n_keys=300, write_interval_median_s=30_000.0)


def test_paired_bootstrap_ci_behaviour():
    lo, hi = S.paired_bootstrap_ci(np.full(10, 0.3), n_boot=2000)
    assert lo == pytest.approx(0.3) and hi == pytest.approx(0.3)
    rng = np.random.default_rng(0)
    noise = rng.normal(0.0, 1.0, 10)
    lo, hi = S.paired_bootstrap_ci(noise - noise.mean(), n_boot=4000)      # mean exactly 0
    assert lo < 0 < hi
    lo, hi = S.paired_bootstrap_ci(rng.normal(0.5, 0.1, 10), n_boot=4000)
    assert lo > 0
    assert S.paired_bootstrap_ci(noise, n_boot=500, seed=3) == S.paired_bootstrap_ci(noise, n_boot=500, seed=3)


def _rows(stale0, stale1, ohr0, ohr1, cap=0.01, mode="mixture"):
    rows = []
    for s, (a, b, c, d) in enumerate(zip(stale0, stale1, ohr0, ohr1)):
        for acc, st, oh in ((0.0, a, c), (1.0, b, d), (0.25, (a + b) / 2, c), (0.5, (a + b) / 2, c),
                            (0.75, b, d)):
            rows.append({"seed": 100 + s, "capacity_frac": cap, "predictor_accuracy": acc,
                         "stale_read_rate": st, "ohr": oh, "notes": f"M7 signal test; mode={mode}"})
    return rows


def test_criteria_pass_when_accurate_predictor_cuts_staleness_without_hit_loss():
    s0 = np.full(10, 0.010)
    s1 = np.full(10, 0.004) + np.linspace(0, 0.0005, 10)
    c = S.evaluate_criteria(_rows(s0, s1, np.full(10, .33), np.full(10, .33)), 0.01)
    assert c.g1 and c.g2 and c.g3 and c.g4 and c.passed
    assert c.n_pos == 10 and c.mean_rel > 0.5 and c.spearman < -0.5


@pytest.mark.parametrize("name,s0,s1,o0,o1,fails", [
    ("no effect", [.01] * 10, [.01] * 10, [.33] * 10, [.33] * 10, {"g1", "g2", "g3"}),
    ("tiny effect", [.010] * 10, [.0095] * 10, [.33] * 10, [.33] * 10, {"g3"}),
    ("hit-ratio cost", [.01] * 10, [.004] * 10, [.34] * 10, [.31] * 10, {"g4"}),
    ("7 of 10 seeds", [.01] * 10, [.004] * 7 + [.012] * 3, [.33] * 10, [.33] * 10, {"g2"}),
])
def test_each_criterion_can_fail_independently(name, s0, s1, o0, o1, fails):
    c = S.evaluate_criteria(_rows(np.array(s0), np.array(s1), np.array(o0), np.array(o1)), 0.01)
    got = {k for k in ("g1", "g2", "g3", "g4") if not getattr(c, k)}
    assert fails <= got, (name, got)
    assert not c.passed


def test_zero_baseline_seeds_are_excluded_from_relative_mean_but_counted():
    s0 = np.array([0.0, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01])
    s1 = np.array([0.0, .004, .004, .004, .004, .004, .004, .004, .004, .004])
    c = S.evaluate_criteria(_rows(s0, s1, np.full(10, .3), np.full(10, .3)), 0.01)
    assert c.n_rel_excluded == 1 and c.mean_rel == pytest.approx(0.6)
    assert c.n_pos == 9


def test_accuracy_one_is_exactly_the_baseline_pred_ttl():
    ctx = EvalContext.build(7, 0.05, "harsh", workload=WL)
    base = evaluate(ctx, next(s for s in registry() if s.name == "pred_ttl:redis"), "test")
    pt = S.accuracy_point(7, 0.05, 1.0, ctx=ctx)
    for k in ("n_reads", "n_stale", "n_miss", "ohr", "stale_read_rate", "utility"):
        assert pt[k] == base[k]
    assert pt["predictor_accuracy"] == 1.0 and "mode=mixture" in pt["notes"]


def test_accuracy_zero_changes_decisions_and_is_deterministic():
    ctx = EvalContext.build(7, 0.05, "harsh", workload=WL)
    a = S.accuracy_point(7, 0.05, 0.0, ctx=ctx)
    b = S.accuracy_point(7, 0.05, 0.0, ctx=ctx)
    one = S.accuracy_point(7, 0.05, 1.0, ctx=ctx)
    assert (a["n_stale"], a["ohr"]) == (b["n_stale"], b["ohr"])
    assert (a["n_stale"], a["ohr"]) != (one["n_stale"], one["ohr"])


def test_regression_diagnostic_targets_align_and_are_finite():
    r = S.feature_regression(7, 0.05, workload=WL, epochs=2)    # asserts y(acc1) == y(acc0) inside
    assert r["n_train"] > 500 and r["n_test"] > 200
    for k in ("r2_acc1", "r2_acc0", "r2_no_predictor_cols", "delta_r2"):
        assert np.isfinite(r[k]) and r[k] < 1.0


def test_numpy_mlp_learns_a_nonlinear_function_and_is_deterministic():
    rng = np.random.default_rng(0)
    X = rng.uniform(-1, 1, (4000, 5)).astype(np.float32)
    y = (np.sin(3 * X[:, 0]) + X[:, 1] * X[:, 2]).astype(np.float32)
    r2 = S.fit_and_score_mlp(X[:3000], y[:3000], X[3000:], y[3000:], seed=1, epochs=25)
    assert r2 > 0.8
    assert r2 == S.fit_and_score_mlp(X[:3000], y[:3000], X[3000:], y[3000:], seed=1, epochs=25)
    noise = rng.normal(size=4000).astype(np.float32)                       # nothing to learn
    assert S.fit_and_score_mlp(X[:3000], noise[:3000], X[3000:], noise[3000:], seed=1, epochs=5) < 0.05
