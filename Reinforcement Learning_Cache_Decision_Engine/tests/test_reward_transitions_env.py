"""M5 gate (reward, transitions, Gymnasium adapter)."""
import dataclasses
import math

import numpy as np
import pytest
from gymnasium.utils.env_checker import check_env

from rlcache.actions import encode_action
from rlcache.config import Config, LatencyConfig, RewardWeights, WorkloadConfig
from rlcache.env import CacheEnv
from rlcache.features_spec import FEATURE_INDEX
from rlcache.reward import compute_reward, utilisation_gate
from rlcache.runner import make_run
from rlcache.sim.engine import R_TRUNC, Insertion
from rlcache.trace.synthetic import generate_synthetic

W = RewardWeights()
CAP = 1_000_000.0
L2_SCORE = math.exp(-300.0 / 8000.0)
ACT = encode_action(1, 2, 1)
FLAT = LatencyConfig(backend_sigma=0.0)


def ins(hits=0, stale_cost=0.0, concurrent=1, byte_seconds=0.0, lat=None):
    i = Insertion(1, 0, 0, 0.0, ACT, 100, 0, True)
    i.hits_l2 = hits
    i.lat_score_sum = hits * L2_SCORE if lat is None else lat
    i.stale_cost_sum = stale_cost
    i.concurrent = concurrent
    i.byte_seconds = byte_seconds
    return i


# ---- reward: hand-computed values and sign tests ------------------------------------------------
def test_reward_hand_computed():
    p = compute_reward(ins(hits=4), W, CAP, 0.0)
    expect = 4 * 1.0 + 0.5 * 4 * L2_SCORE - 1.0 * (1 / (1 + 4))
    assert p.raw == pytest.approx(expect)
    assert p.clipped == pytest.approx(expect / 100.0)          # D-32: learner sees raw / 100
    assert (p.gate, p.stampede, p.stale) == (1.0, 0.0, 0.0)


def test_creating_miss_is_charged_only_through_the_backend_term():
    p = compute_reward(ins(hits=0), W, CAP, 0.0)
    assert p.raw == pytest.approx(-1.0)              # F / F_ref = 1/1, nothing else


def test_stale_read_lowers_reward_and_w_stale_exceeds_w_hit():
    clean = compute_reward(ins(hits=3), W, CAP, 0.0).raw
    dirty = compute_reward(ins(hits=3, stale_cost=0.5), W, CAP, 0.0).raw
    assert dirty == pytest.approx(clean - 3.0 * 0.5)
    one_full_stale_hit = compute_reward(ins(hits=1, stale_cost=1.0), W, CAP, 0.0).raw
    assert one_full_stale_hit < compute_reward(ins(hits=0), W, CAP, 0.0).raw   # worse than no hit


def test_more_hits_raise_reward_monotonically():
    r = [compute_reward(ins(hits=h), W, CAP, 0.0).raw for h in range(0, 8)]
    assert r == sorted(r) and r[-1] > r[0] + 5


def test_memory_term_lowers_reward():
    base = compute_reward(ins(hits=2), W, CAP, 0.0).raw
    held = compute_reward(ins(hits=2, byte_seconds=CAP * 3600.0), W, CAP, 0.0)
    assert held.mem == pytest.approx(0.3)
    assert held.raw == pytest.approx(base - 0.3)


def test_utilisation_gate_and_stampede_outside_gate():
    assert utilisation_gate(0.5) == 1.0 and utilisation_gate(0.9) == 1.0
    assert utilisation_gate(0.95) == pytest.approx(0.5) and utilisation_gate(1.0) == 0.0
    full = compute_reward(ins(hits=5), W, CAP, 1.0)
    assert full.gate == 0.0 and full.raw == pytest.approx(0.0)              # whole bracket gated off
    assert compute_reward(ins(hits=5), W, CAP, 0.95).raw == pytest.approx(
        0.5 * compute_reward(ins(hits=5), W, CAP, 0.0).raw)
    st = compute_reward(ins(hits=5, concurrent=3), W, CAP, 1.0)
    assert st.raw == pytest.approx(-2.0 * 2 / 2.4)                         # stampede NOT gated
    assert compute_reward(ins(hits=5, concurrent=3), W, CAP, 0.0).raw < \
        compute_reward(ins(hits=5, concurrent=1), W, CAP, 0.0).raw


def test_full_cache_lowers_reward_relative_to_empty_for_the_same_outcome():
    """'over-full lowers r': with positive net outcome the gate shrinks reward as util -> 1."""
    lo = compute_reward(ins(hits=6), W, CAP, 0.2).raw
    hi = compute_reward(ins(hits=6), W, CAP, 0.97).raw
    assert hi < lo


def test_scaling_clipping_and_preclip_value_preserved():
    mid = compute_reward(ins(hits=500), W, CAP, 0.0)
    assert mid.clipped == pytest.approx(mid.raw / 100.0) and abs(mid.clipped) < 10   # not saturated
    big = compute_reward(ins(hits=5000), W, CAP, 0.0)
    assert big.clipped == 10.0 and big.raw > 4000                                   # clip binds
    neg = compute_reward(ins(hits=0, concurrent=5000), W, CAP, 0.0)
    assert neg.clipped == -10.0 and neg.raw < -1000
    legacy = RewardWeights(scale=1.0)                                               # literal D-10
    assert compute_reward(ins(hits=500), legacy, CAP, 0.0).clipped == 10.0


def test_gate_can_be_disabled_for_the_ablation_arm():
    off = RewardWeights(gate_enabled=False)
    assert compute_reward(ins(hits=5), off, CAP, 1.0).gate == 1.0
    assert compute_reward(ins(hits=5), off, CAP, 1.0).raw == pytest.approx(
        compute_reward(ins(hits=5), W, CAP, 0.0).raw)
    assert RewardWeights().gate_enabled and RewardWeights().scale == 100.0


# ---- transitions ---------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def syn():
    return generate_synthetic(WorkloadConfig(n_requests=15_000, n_keys=300,
                                             write_interval_median_s=20_000.0, seed=8))


def _cfg(**kw):
    c = dataclasses.replace(Config(), latency=FLAT)
    return dataclasses.replace(c, cache=dataclasses.replace(c.cache, l2_footprint_frac=0.1))


def test_transition_assembly_invariants(syn):
    cfg = _cfg()
    emitted, log = [], []
    state = {"seen": 0, "prev_ts": -1.0}
    rng = np.random.default_rng(0)

    def select(obs, ctx):
        new = emitted[state["seen"]:]
        for tr in new:
            assert np.array_equal(tr.s2, obs)                 # s' = THIS decision's observation
            assert tr.t_close <= ctx.ts                       # closure happened before it
            assert state["prev_ts"] <= tr.t_close             # ...and after the previous decision
        state["seen"] = len(emitted)
        state["prev_ts"] = ctx.ts
        log.append((ctx.idx, obs.copy()))
        return int(rng.integers(0, 45))

    run = make_run(syn, cfg, select, emit=emitted.append, keep_closed=True, seed=3)
    run.go()
    asm, sim = run.asm, run.sim
    # every decision is accounted for exactly once
    assert asm.n_emitted + asm.n_dropped_tail + asm.n_dropped_truncated == sim.n_created
    assert asm.n_emitted == len(emitted) > 500
    by_idx = {i: o for i, o in log}
    ins_by_idx = {i.idx: i for i in sim.closed}
    w, cap = cfg.reward, run.sim.l1.cap + run.sim.l2.cap
    for tr in emitted:
        assert tr.done is False and tr.reason != R_TRUNC
        assert np.array_equal(tr.s, by_idx[tr.idx])           # s = observation at its decision
        assert -w.clip <= tr.r <= w.clip and tr.r == pytest.approx(
            max(-w.clip, min(w.clip, tr.r_raw / w.scale)))
        i = ins_by_idx[tr.idx]
        assert tr.dt == pytest.approx(i.close_time - i.t_decision) and tr.dt >= 0
        ref = compute_reward(i, w, cap, float(tr.s[FEATURE_INDEX["utilisation"]]))
        assert tr.r_raw == pytest.approx(ref.raw)
    assert asm.n_dropped_truncated >= 1                       # end-of-run censoring is explicit


def test_no_transition_is_ever_terminal_and_window_ends_are_not_done(syn):
    run = make_run(syn, _cfg(), lambda o, c: 27, keep=True)
    run.go(0, len(syn) // 2)                                  # a window boundary mid-trace
    assert run.asm.kept and all(not t.done for t in run.asm.kept)


def test_reward_summary_preclip_histogram_is_recorded(syn):
    """D-10: the pre-clip distribution is available for the clip-fraction check."""
    run = make_run(syn, _cfg(), lambda o, c: 27, keep=True)
    run.go()
    raw = np.array([t.r_raw for t in run.asm.kept])
    assert np.all(np.isfinite(raw)) and raw.min() < raw.max()
    clipped = np.mean(np.abs(raw) > RewardWeights().clip)
    assert 0.0 <= clipped <= 1.0                              # value itself is studied in M5 docs


# ---- Gymnasium adapter ---------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def small():
    return generate_synthetic(WorkloadConfig(n_requests=4_000, n_keys=150,
                                             write_interval_median_s=30_000.0, seed=9))


def test_check_env_passes(small):
    check_env(CacheEnv(small, _cfg(), seed=0), skip_render_check=True)


def test_env_reset_is_deterministic_and_obs_in_space(small):
    env = CacheEnv(small, _cfg(), seed=0)
    a, _ = env.reset(seed=5)
    b, _ = env.reset(seed=5)
    assert np.array_equal(a, b) and env.observation_space.contains(a) and a.shape == (19,)


def test_env_episode_semantics_and_reward_accounting(small):
    cfg = _cfg()
    env = CacheEnv(small, cfg, seed=0)
    obs, _ = env.reset(seed=0)
    total, steps, truncated = 0.0, 0, False
    while not truncated:
        obs, r, terminated, truncated, info = env.step(27)
        assert terminated is False and math.isfinite(r) and env.observation_space.contains(obs)
        total += r
        steps += 1
    assert steps > 100
    with pytest.raises(RuntimeError):
        env.step(0)                                           # episode over
    # the same constant policy through the engine: closed-insertion rewards sum to the env total
    run = make_run(small, cfg, lambda o, c: 27, keep_closed=True, seed=0, learn_normalizer=True)
    run.go()
    cap = run.sim.l1.cap + run.sim.l2.cap
    expected = sum(compute_reward(i, cfg.reward, cap, float(i.payload[0][FEATURE_INDEX["utilisation"]])).clipped
                   for i in run.sim.closed if i.close_reason != R_TRUNC)
    assert total == pytest.approx(expected, rel=1e-9, abs=1e-9)
    assert run.asm.n_decisions == steps


# ---- Amendment M9-e: successor="same_key" -------------------------------------------------------
def test_same_key_successor_is_that_keys_next_decision(syn):
    cfg = _cfg()
    emitted, obs_by_key_idx = [], {}
    rng = np.random.default_rng(1)

    def select(obs, ctx):
        obs_by_key_idx[(ctx.key, ctx.idx)] = (obs.copy(), ctx.ts)
        return int(rng.integers(0, 45))

    run = make_run(syn, cfg, select, emit=emitted.append, seed=3, successor="same_key")
    run.go()
    asm = run.asm
    assert asm.n_emitted == len(emitted) > 300
    # every decision is accounted for exactly once (dropped_tail now includes per-key waiters)
    assert asm.n_emitted + asm.n_dropped_tail + asm.n_dropped_truncated == run.sim.n_created
    decisions_of = {}
    for (k, i) in sorted(obs_by_key_idx, key=lambda x: x[1]):
        decisions_of.setdefault(k, []).append(i)
    for tr in emitted:
        assert tr.done is False
        later = [i for i in decisions_of[tr.key] if i > tr.idx and obs_by_key_idx[(tr.key, i)][1] >= tr.t_close]
        assert later, "successor must exist"
        nxt = later[0]                                   # the key's FIRST decision after closure
        assert np.array_equal(tr.s2, obs_by_key_idx[(tr.key, nxt)][0])


def test_default_successor_unchanged_and_bad_value_rejected(syn):
    cfg = _cfg()
    a, b = [], []
    for out, kw in ((a, {}), (b, {"successor": "any"})):
        rng = np.random.default_rng(2)
        make_run(syn, cfg, lambda o, c, r=rng: int(r.integers(0, 45)), emit=out.append, seed=4, **kw).go()
    assert len(a) == len(b) > 300
    assert all(np.array_equal(x.s2, y.s2) and x.r == y.r for x, y in zip(a, b))
    with pytest.raises(ValueError):
        make_run(syn, cfg, lambda o, c: 0, successor="next")
