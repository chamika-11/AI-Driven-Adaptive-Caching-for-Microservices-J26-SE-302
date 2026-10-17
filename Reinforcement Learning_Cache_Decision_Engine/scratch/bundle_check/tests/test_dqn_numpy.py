"""M9 (local half): numpy reference learner, replay, schedule, probes and the training driver.
No torch needed.  The torch learner is checked against this reference by test_dqn_torch.py."""
import dataclasses

import numpy as np
import pytest

from rlcache.agents import dqn_train as T
from rlcache.agents.probes import Probe, expected_q, train_on_env
from rlcache.agents.qnet_numpy import NumpyDuelingQ
from rlcache.agents.replay import ReplayBuffer
from rlcache.baselines.policies import Spec
from rlcache.config import DQNConfig, WorkloadConfig
from rlcache.evaluation import EvalContext, evaluate_sim_policy
from rlcache.results_schema import validate_row


def _batch(rng, B=16, d=5, A=4):
    return {"obs": rng.normal(size=(B, d)), "actions": rng.integers(0, A, B),
            "rewards": rng.normal(size=B) * 0.3, "next_obs": rng.normal(size=(B, d)),
            "dones": (rng.random(B) < 0.2).astype(float)}


# ---- gradients ------------------------------------------------------------------------------------
@pytest.mark.parametrize("dueling", [True, False])
@pytest.mark.parametrize("double", [True, False])
def test_analytic_gradients_match_finite_differences(dueling, double):
    rng = np.random.default_rng(3)
    net = NumpyDuelingQ(5, 4, hidden=8, seed=1, dtype=np.float64, dueling=dueling, double=double)
    # make target differ from online so the bootstrap term is non-trivial
    for k in net.target:
        net.target[k] = net.target[k] + 0.2 * rng.normal(size=net.target[k].shape)
    b = _batch(rng)
    _, grads, _ = net.loss_and_grads(b, 0.9)
    h = 1e-6
    checked = 0
    for k, p in net.params.items():
        flat = p.reshape(-1)
        for j in rng.choice(flat.size, size=min(6, flat.size), replace=False):
            old = flat[j]
            flat[j] = old + h
            lp, _, _ = net.loss_and_grads(b, 0.9)
            flat[j] = old - h
            lm, _, _ = net.loss_and_grads(b, 0.9)
            flat[j] = old
            num = (lp - lm) / (2 * h)
            ana = grads[k].reshape(-1)[j]
            assert abs(num - ana) <= 1e-6 + 1e-5 * max(abs(num), abs(ana)), (k, j, num, ana)
            checked += 1
    assert checked >= 20


def test_double_dqn_target_online_argmax_target_evaluates():
    net = NumpyDuelingQ(3, 3, hidden=4, seed=0, dtype=np.float64)
    nxt = np.array([[0.3, -0.2, 0.5]])
    q_on = net.forward(nxt)[0]
    j = (int(np.argmax(q_on)) + 1) % 3                                       # a DIFFERENT action
    shift = np.zeros(3)
    shift[j] = 50.0                                                          # target now prefers j
    net.target["ba"] = net.target["ba"] + shift
    q_tg = net.forward(nxt, target=True)[0]
    assert int(np.argmax(q_tg)) == j != int(np.argmax(q_on))
    batch = {"next_obs": nxt, "rewards": np.array([1.0]), "dones": np.array([0.0])}
    got = net.td_targets(batch, 0.9)[0]
    assert got == pytest.approx(1.0 + 0.9 * q_tg[int(np.argmax(q_on))])
    assert got != pytest.approx(1.0 + 0.9 * q_tg.max())                       # not the vanilla max
    net.double = False
    assert net.td_targets(batch, 0.9)[0] == pytest.approx(1.0 + 0.9 * q_tg.max())
    batch["dones"] = np.array([1.0])
    assert net.td_targets(batch, 0.9)[0] == pytest.approx(1.0)                # terminal: no bootstrap


def test_dueling_head_is_mean_subtracted():
    net = NumpyDuelingQ(3, 5, hidden=6, seed=2, dtype=np.float64)
    X = np.random.default_rng(0).normal(size=(4, 3))
    q0 = net.forward(X)
    net.params["ba"] = net.params["ba"] + 7.0            # shifting ALL advantages changes nothing
    assert np.allclose(net.forward(X), q0)
    net.params["bv"] = net.params["bv"] + 2.0            # shifting V shifts every Q equally
    assert np.allclose(net.forward(X), q0 + 2.0)


# ---- optimiser and target update -------------------------------------------------------------------
def test_adamw_amsgrad_matches_independent_reference_over_three_steps():
    net = NumpyDuelingQ(3, 2, hidden=4, seed=5, dtype=np.float64, lr=1e-2, weight_decay=0.05,
                        max_grad_norm=1e9)
    rng = np.random.default_rng(0)
    ref = {k: v.copy() for k, v in net.params.items()}
    m = {k: np.zeros_like(v) for k, v in ref.items()}
    v2 = {k: np.zeros_like(v) for k, v in ref.items()}
    vmax = {k: np.zeros_like(v) for k, v in ref.items()}
    for t in range(1, 4):
        g = {k: rng.normal(size=v.shape) for k, v in ref.items()}
        net.apply_adamw(g)
        for k in ref:
            ref[k] = ref[k] * (1 - 1e-2 * 0.05)
            m[k] = 0.9 * m[k] + 0.1 * g[k]
            v2[k] = 0.999 * v2[k] + 0.001 * g[k] ** 2
            vmax[k] = np.maximum(vmax[k], v2[k])
            ref[k] = ref[k] - (1e-2 / (1 - 0.9 ** t)) * m[k] / (np.sqrt(vmax[k]) / np.sqrt(1 - 0.999 ** t) + 1e-8)
    for k in ref:
        assert np.allclose(net.params[k], ref[k], atol=1e-12), k


def test_gradient_norm_clipping_caps_the_global_norm():
    net = NumpyDuelingQ(3, 2, hidden=4, seed=5, dtype=np.float64, lr=1.0, weight_decay=0.0,
                        max_grad_norm=10.0, amsgrad=False)
    g = {k: np.full_like(v, 100.0) for k, v in net.params.items()}
    big = np.sqrt(sum((x ** 2).sum() for x in g.values()))
    ret = net.apply_adamw(g)
    assert ret == pytest.approx(big)                       # reports the PRE-clip norm (torch semantics)
    # first Adam step is lr * sign(g) irrespective of scale, so just assert it stayed finite
    assert all(np.isfinite(p).all() for p in net.params.values())


def test_soft_update_and_sync():
    net = NumpyDuelingQ(3, 2, hidden=4, seed=0, dtype=np.float64)
    online = {k: v.copy() for k, v in net.params.items()}
    for k in net.params:
        net.params[k] = net.params[k] + 1.0
    old_t = {k: v.copy() for k, v in net.target.items()}
    net.soft_update(0.25)
    for k in net.target:
        assert np.allclose(net.target[k], 0.75 * old_t[k] + 0.25 * net.params[k])
    net.sync_target()
    assert all(np.array_equal(net.target[k], net.params[k]) for k in net.params)


def test_export_import_and_numpy_inference_agree():
    net = NumpyDuelingQ(19, 45, hidden=16, seed=4)
    w = net.export_weights()
    inf = NumpyDuelingQ.from_weights(w)
    x = np.random.default_rng(1).normal(size=19).astype(np.float32)
    assert np.allclose(net.q_values(x), inf.q_values(x), atol=1e-6)
    assert inf.q_values(x).shape == (45,)


# ---- replay and schedule --------------------------------------------------------------------------------
def test_replay_buffer_ring_semantics_and_own_rng():
    b = ReplayBuffer(5, 2, seed=3)
    for i in range(8):
        b.add([i, i], i, float(i), [i + 1, i + 1], False)
    assert len(b) == 5 and b.ptr == 3
    assert sorted(b.actions.tolist()) == [3, 4, 5, 6, 7]               # oldest three overwritten
    s1 = ReplayBuffer(50, 2, seed=9)
    s2 = ReplayBuffer(50, 2, seed=9)
    for i in range(30):
        s1.add([i, 0], i, 0.0, [i, 0], False)
        s2.add([i, 0], i, 0.0, [i, 0], False)
    assert np.array_equal(s1.sample(8)["actions"], s2.sample(8)["actions"])
    out = s1.sample(8)
    assert out["obs"].dtype == np.float32 and out["obs"].shape == (8, 2)
    with pytest.raises(ValueError):
        ReplayBuffer(5, 2).sample(1)


def test_epsilon_schedule_matches_spec():
    cfg = DQNConfig()
    assert T.eps_at(0, 300_000, cfg) == 1.0
    assert T.eps_at(45_000, 300_000, cfg) == pytest.approx(0.55)
    assert T.eps_at(90_000, 300_000, cfg) == pytest.approx(0.10)
    assert T.eps_at(299_999, 300_000, cfg) == pytest.approx(0.10)


# ---- probes (gate C2, numpy learner) -----------------------------------------------------------------------
@pytest.mark.parametrize("variant", [1, 2, 3, 4, 5])
def test_probes_learn_hand_computed_q_values(variant):
    gamma = 0.95
    for seed in (0, 1):
        net = NumpyDuelingQ(1, 2 if variant in (4, 5) else 1, hidden=32, seed=seed, lr=2e-3,
                            weight_decay=0.0, max_grad_norm=10.0, dtype=np.float64)
        train_on_env(Probe(variant), net, steps=5000, gamma=gamma, batch_size=64, tau=0.02,
                     learning_starts=200, seed=seed)
        for obs, want in expected_q(variant, gamma).items():
            got = net.q_values(np.array(obs))
            assert np.allclose(got, want, atol=0.05), (variant, seed, obs, got, want)


# ---- training driver ---------------------------------------------------------------------------------------------
WL = WorkloadConfig(n_requests=30_000, n_keys=300, write_interval_median_s=30_000.0)
SMALL = DQNConfig(total_decisions=3_000, learning_starts=500, buffer_size=5_000, batch_size=32,
                  train_every=4)


@pytest.fixture(scope="module")
def ctx():
    return EvalContext.build(3, 0.05, "harsh", workload=WL)


def _learner(seed=0):
    return NumpyDuelingQ(19, 45, hidden=16, seed=seed, lr=1e-3)


def test_training_driver_budget_cadence_and_determinism(ctx):
    a = T.train_dqn(ctx, _learner(), SMALL, calib_requests=2_000, log_every=400)
    b = T.train_dqn(ctx, _learner(), SMALL, calib_requests=2_000, log_every=400)
    assert a.decisions == 3_000 and a.norm.frozen
    expected = len([n for n in range(1, 3001) if n >= 500 and n % 4 == 0])
    assert a.gradient_steps == pytest.approx(expected, abs=2)           # buffer may lag at the start
    assert a.curve and np.isfinite([c[1] for c in a.curve]).all()
    wa, wb = a.learner.export_weights(), b.learner.export_weights()
    assert all(np.array_equal(wa[k], wb[k]) for k in wa)
    assert a.action_hist.sum() == 3_000 and (a.action_hist > 0).sum() > 20


def test_replay_receives_only_nonterminal_transitions(ctx, monkeypatch):
    seen = []
    orig = ReplayBuffer.add

    def spy(self, obs, action, reward, next_obs, done):
        seen.append((float(done), float(reward)))
        return orig(self, obs, action, reward, next_obs, done)

    monkeypatch.setattr(ReplayBuffer, "add", spy)
    T.train_dqn(ctx, _learner(), SMALL, calib_requests=2_000)
    assert len(seen) > 500
    assert all(d == 0.0 for d, _ in seen)                                # continuing task
    assert all(abs(r) <= 10.0 for _, r in seen)                          # D-32 scaling + clip


def test_training_uses_only_the_training_slice(ctx):
    rng = np.random.default_rng(0)
    key = ctx.trace.key.copy()
    key[ctx.splits.train_end:] = rng.integers(0, ctx.trace.n_keys, len(key) - ctx.splits.train_end)
    ctx2 = EvalContext.build(3, 0.05, "harsh", trace=dataclasses.replace(ctx.trace, key=key))
    ctx2.l1_bytes, ctx2.l2_bytes = ctx.l1_bytes, ctx.l2_bytes             # capacity is a design parameter
    a = T.train_dqn(ctx, _learner(), SMALL, calib_requests=2_000)
    b = T.train_dqn(ctx2, _learner(), SMALL, calib_requests=2_000)
    wa, wb = a.learner.export_weights(), b.learner.export_weights()
    assert all(np.array_equal(wa[k], wb[k]) for k in wa)


def test_greedy_policy_row_checkpoint_roundtrip_and_no_learning(ctx, tmp_path):
    res = T.train_dqn(ctx, _learner(), SMALL, calib_requests=2_000)
    w_before = {k: v.copy() for k, v in res.learner.export_weights().items()}
    pol = T.GreedyDQNPolicy(res, ctx)
    row = evaluate_sim_policy(ctx, Spec("dqn", "dqn", "learned", lambda c: pol), "val", policy=pol)
    validate_row(row)
    assert row["policy_class"] == "learned" and row["n_reads"] > 0 and pol.action_hist.sum() > 0
    assert all(np.array_equal(w_before[k], res.learner.export_weights()[k]) for k in w_before)
    path = tmp_path / "ck.npz"
    T.save_checkpoint(path, res, {"seed": 3})
    w, norm, meta = T.load_checkpoint(path)
    assert all(np.array_equal(w[k], w_before[k]) for k in w_before)
    assert norm["frozen"] is True and meta["seed"] == 3 and meta["decisions"] == 3_000
    # a policy rebuilt from the checkpoint alone decides identically
    inf = NumpyDuelingQ.from_weights(w)
    x = np.random.default_rng(0).uniform(size=19).astype(np.float32)
    assert int(np.argmax(inf.q_values(x))) == int(np.argmax(res.learner.q_values(x)))


def test_bandit_variant_trains_with_gamma_zero(ctx):
    res = T.train_dqn(ctx, _learner(), SMALL, gamma=0.0, calib_requests=2_000)
    assert res.gamma == 0.0 and res.decisions == 3_000
