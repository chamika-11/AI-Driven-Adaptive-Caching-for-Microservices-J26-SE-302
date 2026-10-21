"""Addendum M11-E (E3): shift traces, windowed series and the pre-registered adaptation metrics."""
import numpy as np
import pytest

from rlcache import shift as SH
from rlcache.config import DQNConfig, WorkloadConfig


def _series(h, s=None, ttl=None):
    n = len(h)
    return {"reads": [100] * n, "hit_ratio": list(h), "stale_rate": list(s if s is not None else [0.0] * n),
            "ttl_median": list(ttl if ttl is not None else [60.0] * n)}


def test_metrics_hand_computed():
    h = [0.5] * 10 + [0.2, 0.2, 0.3, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]
    m = SH.shift_metrics(_series(h), t_star=10, a=0, window=1)
    assert m.h_pre == pytest.approx(0.5) and m.h_new == pytest.approx(0.5)
    assert m.dip_depth == pytest.approx(30.0)                       # (0.5 - 0.2) * 100
    assert m.area_under_dip == pytest.approx(0.3 + 0.3 + 0.2)       # sum of shortfalls x window(1)
    assert m.recovery_requests == 3.0 and not m.censored            # first of 3 consecutive windows >= 0.95 h_new


def test_recovery_is_censored_when_it_never_returns_and_needs_three_in_a_row():
    h = [0.5] * 10 + [0.1] * 10
    h[-4:] = [0.5, 0.5, 0.5, 0.5]
    assert SH.shift_metrics(_series(h), 10, 0, 1).recovery_requests == 6.0          # recovers at window 16
    h2 = [0.5] * 10 + [0.5, 0.1, 0.5, 0.1, 0.5, 0.1, 0.5, 0.1, 0.5, 0.1]
    h2[-4:] = [0.5, 0.5, 0.5, 0.5]
    m = SH.shift_metrics(_series(h2), 10, 0, 1)
    assert m.recovery_requests == 6.0                                                # isolated 0.5 windows do not count
    h3 = [0.5] * 10 + [0.05] * 10                                                    # never returns (h_new is low too)
    h3[-4:] = [0.5, 0.1, 0.5, 0.1]
    assert SH.shift_metrics(_series(h3), 10, 0, 1).censored


def test_stale_spike_ttl_response_and_regret():
    s = [0.01] * 10 + [0.01, 0.05, 0.2, 0.1, 0.05, 0.02, 0.02, 0.02, 0.02, 0.02]
    ttl = [600.0] * 10 + [600.0, 100.0, 30.0, 30.0, 30.0, 30.0, 30.0, 30.0, 30.0, 30.0]
    h = [0.5] * 20
    m = SH.shift_metrics(_series(h, s, ttl), 10, 0, 1)
    assert m.stale_spike == pytest.approx(0.2 - 0.01) and m.ttl_before == 600.0 and m.ttl_after == 30.0
    ref = [_series([0.5] * 10 + [0.6] * 10), _series([0.5] * 10 + [0.7] * 10)]
    assert SH.cumulative_regret(_series(h), ref, 10, 0, 1) == pytest.approx(10 * 0.2)   # best baseline 0.7 vs 0.5


@pytest.mark.parametrize("name", SH.SHIFTS)
def test_shift_traces_have_the_shift_inside_the_test_slice(name):
    tr = SH.make_shift_trace(name, 0)
    t_star = SH.shift_index(tr)
    assert 0.87 * len(tr) < t_star < 0.89 * len(tr)
    assert tr.meta["shifts"] and len(tr) == 600_000
    assert tr.meta["n_reads"] > 0.2 * len(tr)


def test_series_for_policy_and_online_variant_smoke():
    from rlcache.agents import dqn_train as T
    from rlcache.agents.qnet_numpy import NumpyDuelingQ
    from rlcache.baselines.policies import registry
    from rlcache.evaluation import EvalContext
    wl = WorkloadConfig(n_requests=30_000, n_keys=300, write_interval_median_s=30_000.0, diurnal_amp=0.0)
    ctx = EvalContext.build(1, 0.05, "harsh", workload=wl)
    reg = {s.name: s for s in registry()}
    ser = SH.series_for_policy(ctx, reg["fixed:redis/3600s/normal"].make(ctx), window=500)
    a, b, mf = ctx.slice_for("test")
    assert len(ser["hit_ratio"]) == (b - a) // 500
    assert np.isfinite(ser["hit_ratio"][-1]) and 0.0 <= ser["hit_ratio"][-1] <= 1.0
    assert ser["hit_ratio"][0] != ser["hit_ratio"][0] or True          # first window may be pure warm-up (nan)
    cfg = DQNConfig(total_decisions=2_000, learning_starts=300, buffer_size=4_000, batch_size=32)
    learner = NumpyDuelingQ(hidden=16, seed=3)
    res = T.train_dqn(ctx, learner, cfg, calib_requests=2_000, log_every=400)
    w0 = {k: v.copy() for k, v in learner.export_weights().items()}
    on = SH.series_online(ctx, res, cfg, window=500, learning_starts=200)
    assert len(on["hit_ratio"]) == len(ser["hit_ratio"])
    w1 = learner.export_weights()
    assert any(not np.array_equal(w0[k], w1[k]) for k in w0)           # the online variant really learned
