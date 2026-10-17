"""Correctness gates C1 (torch == numpy reference) and C2 (probe environments).

Pre-registered in docs/PREREGISTRATION.md, Addendum M9.  torch is imported lazily so the module
can be imported anywhere; the torch checks need a working torch (Colab).
"""
from __future__ import annotations

import numpy as np

from .probes import Probe, expected_q, train_on_env
from .qnet_numpy import NumpyDuelingQ

GAMMA = 0.95
PROBE_TOL = 0.05
C1_TOL = {"q_abs": 1e-5, "loss_rel": 1e-4, "grad_rel": 1e-3, "weights_abs": 1e-4}


def _rel_max(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.abs(a - b).max() / (np.abs(b).max() + 1e-12))


def check_equivalence(seed: int = 0, hidden: int = 32, dueling: bool = True, double: bool = True,
                      n_steps: int = 5) -> dict:
    """C1: PyTorch learner vs numpy reference on identical weights and batches."""
    from .dqn_torch import TorchLearner

    rng = np.random.default_rng(seed)
    kw = dict(obs_dim=19, n_actions=45, hidden=hidden, dueling=dueling, double=double, lr=2.5e-4,
              weight_decay=0.01, amsgrad=True, max_grad_norm=10.0)
    ref = NumpyDuelingQ(seed=seed, dtype=np.float32, **kw)
    tl = TorchLearner(seed=seed + 1, **kw)
    w_online = ref.export_weights()
    # a DIFFERENT target network, so the bootstrap term is exercised
    other = NumpyDuelingQ(seed=seed + 7, dtype=np.float32, **kw).export_weights()
    ref.target = {k: v.astype(np.float32).copy() for k, v in other.items()}
    tl.load_weights(other, target=True)
    tl.load_weights(w_online, target=False)

    X = rng.normal(size=(64, 19)).astype(np.float32)
    q_diff = max(float(np.abs(tl.forward_np(X) - ref.forward(X)).max()),
                 float(np.abs(tl.forward_np(X, target=True) - ref.forward(X, target=True)).max()))

    def batch():
        return {"obs": rng.normal(size=(128, 19)).astype(np.float32),
                "actions": rng.integers(0, 45, 128), "rewards": (rng.normal(size=128) * 0.5).astype(np.float32),
                "next_obs": rng.normal(size=(128, 19)).astype(np.float32),
                "dones": (rng.random(128) < 0.1).astype(np.float32)}

    b = batch()
    loss_ref, g_ref, _ = ref.loss_and_grads(b, GAMMA)
    loss_t, g_t, _ = tl.loss_and_grads(b, GAMMA)
    loss_rel = abs(float(loss_t.item()) - loss_ref) / (abs(loss_ref) + 1e-12)
    grad_rel = 0.0
    for tname, (nname, transpose) in TorchLearner.GRAD_MAP.items():
        if tname not in g_t:
            continue
        gt = g_t[tname].numpy()
        gt = gt.T if transpose else gt
        grad_rel = max(grad_rel, _rel_max(gt, g_ref[nname]))

    # n AdamW steps from identical weights (clipping included), target held fixed
    ref2 = NumpyDuelingQ(seed=seed, dtype=np.float32, **kw)
    ref2.load_weights(w_online, target=False)
    ref2.target = {k: v.astype(np.float32).copy() for k, v in other.items()}
    tl2 = TorchLearner(seed=seed + 1, **kw)
    tl2.load_weights(other, target=True)
    tl2.load_weights(w_online, target=False)
    for _ in range(n_steps):
        bb = batch()
        ref2.train_step(bb, GAMMA)
        tl2.train_step(bb, GAMMA)
    wt, wr = tl2.export_weights(), ref2.export_weights()
    w_diff = max(float(np.abs(wt[k] - wr[k]).max()) for k in wr)

    out = {"q_abs_diff": q_diff, "loss_rel_diff": loss_rel, "grad_rel_diff": grad_rel,
           "weights_abs_diff_after_steps": w_diff, "n_steps": n_steps,
           "dueling": dueling, "double": double}
    out["pass"] = bool(q_diff < C1_TOL["q_abs"] and loss_rel < C1_TOL["loss_rel"]
                       and grad_rel < C1_TOL["grad_rel"] and w_diff < C1_TOL["weights_abs"])
    return out


def check_probes(backend: str = "numpy", seeds=(0, 1, 2), steps: int = 5000) -> list[dict]:
    """C2: every probe's learned Q within 0.05 of the hand-computed value."""
    rows = []
    for variant in (1, 2, 3, 4, 5):
        for seed in seeds:
            n_act = 2 if variant in (4, 5) else 1
            kw = dict(obs_dim=1, n_actions=n_act, hidden=32, seed=seed, lr=2e-3, weight_decay=0.0,
                      max_grad_norm=10.0)
            if backend == "torch":
                from .dqn_torch import TorchLearner
                learner = TorchLearner(**kw)
            else:
                learner = NumpyDuelingQ(dtype=np.float64, **kw)
            train_on_env(Probe(variant), learner, steps=steps, gamma=GAMMA, batch_size=64, tau=0.02,
                         learning_starts=200, seed=seed)
            worst, detail = 0.0, []
            for obs, want in expected_q(variant, GAMMA).items():
                got = np.asarray(learner.q_values(np.array(obs, dtype=np.float32)), dtype=float)
                err = float(np.abs(got - np.asarray(want)).max())
                worst = max(worst, err)
                detail.append((obs, [round(float(x), 3) for x in got], want))
            rows.append({"probe": variant, "seed": seed, "max_abs_err": worst, "pass": worst < PROBE_TOL,
                         "detail": detail, "backend": backend})
    return rows
