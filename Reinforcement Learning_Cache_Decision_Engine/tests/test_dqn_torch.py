"""M9 (Colab half): the PyTorch learner against the numpy reference (gate C1), the probe
environments (gate C2), and the training driver with the torch learner.

Skipped automatically where torch cannot be imported (e.g. the development machine, C-47)."""
import numpy as np
import pytest

try:                                    # ImportError normally; OSError under Windows App Control
    import torch  # noqa: F401
    _HAVE, _WHY = True, ""
except Exception as e:                  # noqa: BLE001
    _HAVE, _WHY = False, repr(e)

pytestmark = pytest.mark.skipif(not _HAVE, reason=f"torch unavailable: {_WHY}")


def test_c1_forward_loss_gradients_and_adamw_match_numpy_reference():
    from rlcache.agents.dqn_checks import check_equivalence
    for dueling, double in ((True, True), (True, False), (False, True)):
        r = check_equivalence(seed=0, dueling=dueling, double=double)
        assert r["pass"], r


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_c2_probes_with_the_torch_learner(seed):
    from rlcache.agents.dqn_checks import check_probes
    for row in check_probes("torch", seeds=(seed,)):
        assert row["pass"], row


def test_target_network_only_moves_on_soft_update():
    from rlcache.agents.dqn_torch import TorchLearner
    rng = np.random.default_rng(0)
    tl = TorchLearner(obs_dim=19, n_actions=45, hidden=16, seed=0)
    b = {"obs": rng.normal(size=(32, 19)), "actions": rng.integers(0, 45, 32),
         "rewards": rng.normal(size=32), "next_obs": rng.normal(size=(32, 19)),
         "dones": np.zeros(32)}
    t0 = [p.detach().clone() for p in tl.target.parameters()]
    n0 = [p.detach().clone() for p in tl.net.parameters()]
    tl.train_step(b, 0.95)
    assert all(torch.equal(a, p) for a, p in zip(t0, tl.target.parameters()))      # untouched
    assert any(not torch.equal(a, p) for a, p in zip(n0, tl.net.parameters()))     # online moved
    tl.soft_update(0.25)
    for a, p, o in zip(t0, tl.target.parameters(), tl.net.parameters()):
        assert torch.allclose(p, 0.75 * a + 0.25 * o, atol=1e-6)
    assert all(not q.requires_grad for q in tl.target.parameters())


def test_same_seed_same_training_trajectory():
    from rlcache.agents.dqn_torch import TorchLearner
    def run():
        rng = np.random.default_rng(5)
        tl = TorchLearner(obs_dim=19, n_actions=45, hidden=16, seed=3)
        for _ in range(5):
            b = {"obs": rng.normal(size=(32, 19)), "actions": rng.integers(0, 45, 32),
                 "rewards": rng.normal(size=32), "next_obs": rng.normal(size=(32, 19)),
                 "dones": np.zeros(32)}
            tl.train_step(b, 0.95)
            tl.soft_update(0.005)
        return tl.export_weights()
    a, b = run(), run()
    assert all(np.array_equal(a[k], b[k]) for k in a)


def test_training_driver_runs_with_the_torch_learner():
    from rlcache.agents import dqn_train as T
    from rlcache.agents.dqn_torch import TorchLearner
    from rlcache.baselines.policies import Spec
    from rlcache.config import DQNConfig, WorkloadConfig
    from rlcache.evaluation import EvalContext, evaluate_sim_policy
    from rlcache.results_schema import validate_row

    wl = WorkloadConfig(n_requests=30_000, n_keys=300, write_interval_median_s=30_000.0)
    ctx = EvalContext.build(3, 0.05, "harsh", workload=wl)
    cfg = DQNConfig(total_decisions=3_000, learning_starts=500, buffer_size=5_000, batch_size=32)
    res = T.train_dqn(ctx, TorchLearner(hidden=16, seed=3), cfg, calib_requests=2_000, log_every=400)
    assert res.decisions == 3_000 and res.gradient_steps > 100 and res.curve
    assert np.isfinite([c[1] for c in res.curve]).all()
    pol = T.GreedyDQNPolicy(res, ctx)                    # numpy inference path from exported weights
    row = evaluate_sim_policy(ctx, Spec("dqn", "dqn", "learned", lambda c: pol), "val", policy=pol)
    validate_row(row)
    x = np.random.default_rng(0).uniform(size=19).astype(np.float32)
    assert np.allclose(res.learner.q_values(x), pol.net.q_values(x), atol=1e-5)


def test_hard_target_sync_copies_online_weights():
    from rlcache.agents.dqn_torch import TorchLearner
    rng = np.random.default_rng(0)
    tl = TorchLearner(obs_dim=4, n_actions=2, hidden=16, seed=0)
    b = {"obs": rng.normal(size=(16, 4)), "actions": rng.integers(0, 2, 16),
         "rewards": rng.normal(size=16), "next_obs": rng.normal(size=(16, 4)), "dones": np.zeros(16)}
    for _ in range(3):
        tl.train_step(b, 0.99)
    assert any(not torch.equal(p, t) for p, t in zip(tl.net.parameters(), tl.target.parameters()))
    tl.sync_target()
    assert all(torch.equal(p, t) for p, t in zip(tl.net.parameters(), tl.target.parameters()))
