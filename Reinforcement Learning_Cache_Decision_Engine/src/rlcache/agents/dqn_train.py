"""Training driver, greedy policy and checkpoints for the DQN (M9; Addendum M9).

Backend-agnostic: any learner exposing ``q_values(obs)``, ``train_step(batch, gamma)``,
``soft_update(tau)`` and ``export_weights()`` works (``NumpyDuelingQ`` or ``TorchLearner``).
Everything around the learner (calibration pass, frozen normaliser, closure -> transition ->
replay, epsilon schedule, cold replays of the training slice) is the same as the tabular agent.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..config import N_ACTIONS, N_FEATURES, DQNConfig
from ..evaluation import EvalContext
from ..features import FeatureTracker, Normalizer
from ..runner import make_run
from .qnet_numpy import NumpyDuelingQ
from .replay import ReplayBuffer


class _Stop(Exception):
    pass


def eps_at(n: int, total: int, cfg: DQNConfig) -> float:
    """Linear ``eps_start -> eps_end`` over the first ``eps_decay_frac`` of training, then held."""
    frac = min(1.0, n / max(cfg.eps_decay_frac * total, 1.0))
    return cfg.eps_start + frac * (cfg.eps_end - cfg.eps_start)


@dataclass
class DQNResult:
    learner: object
    norm: Normalizer
    decisions: int
    epochs: int
    gamma: float
    gradient_steps: int
    action_hist: np.ndarray
    curve: list = field(default_factory=list)       # (decision, loss, q_mean, q_max, target_mean)
    diag: dict = field(default_factory=dict)


def train_dqn(ctx: EvalContext, learner, cfg: DQNConfig | None = None, gamma: float | None = None,
              total_decisions: int | None = None, calib_requests: int = 40_000,
              log_every: int = 5_000, verbose: bool = False, successor: str = "any") -> DQNResult:
    cfg = cfg or DQNConfig()
    gamma = cfg.gamma if gamma is None else gamma
    total = cfg.total_decisions if total_decisions is None else total_decisions
    seed = ctx.seed
    rng = np.random.default_rng([seed, 23])
    a0, b0 = ctx.splits.train
    kw = dict(predictor=ctx.predictor, l1_capacity_bytes=ctx.l1_bytes, l2_capacity_bytes=ctx.l2_bytes)

    # ---- calibration pass: fit + FREEZE the normaliser (training slice only) ----------------
    norm = Normalizer(ctx.cfg.features)
    make_run(ctx.trace, ctx.cfg, lambda o, c: int(rng.integers(0, N_ACTIONS)), normalizer=norm,
             learn_normalizer=True, seed=seed, **kw).go(a0, min(b0, a0 + calib_requests))
    norm.freeze()

    # ---- learning ----------------------------------------------------------------------------
    buf = ReplayBuffer(cfg.buffer_size, N_FEATURES, seed=seed)
    state = {"n": 0, "grad": 0}
    hist = np.zeros(N_ACTIONS, dtype=np.int64)
    curve: list = []

    def select(obs, c):
        if state["n"] >= total:
            raise _Stop
        if rng.random() < eps_at(state["n"], total, cfg):
            a = int(rng.integers(0, N_ACTIONS))
        else:
            a = int(np.argmax(learner.q_values(obs)))
        state["n"] += 1
        hist[a] += 1
        n = state["n"]
        if n >= cfg.learning_starts and n % cfg.train_every == 0 and len(buf) >= cfg.batch_size:
            m = learner.train_step(buf.sample(cfg.batch_size), gamma)
            learner.soft_update(cfg.tau)
            state["grad"] += 1
            if state["grad"] % max(log_every // cfg.train_every, 1) == 0:
                curve.append((n, m["loss"], m["q_mean"], m["q_max"], m["target_mean"]))
                if verbose:
                    print(f"  dec {n:>7} eps {eps_at(n, total, cfg):.2f} loss {m['loss']:.5f} "
                          f"Qmean {m['q_mean']:.3f} Qmax {m['q_max']:.3f}", flush=True)
        return a

    def emit(tr):
        buf.add(tr.s, tr.a, tr.r, tr.s2, False)       # continuing task: never terminal (R-S5)

    dropped = {"tail": 0, "emitted": 0}
    epochs = 0
    while state["n"] < total:
        run = make_run(ctx.trace, ctx.cfg, select, normalizer=norm, learn_normalizer=False,
                       emit=emit, seed=seed * 1000 + epochs, successor=successor, **kw)
        try:
            run.go(a0, b0)
        except _Stop:
            pass
        dropped["tail"] += run.asm.n_dropped_tail
        dropped["emitted"] += run.asm.n_emitted
        epochs += 1
        if epochs > 400:
            raise RuntimeError("training slice yields too few decisions")
    return DQNResult(learner, norm, state["n"], epochs, gamma, state["grad"], hist, curve,
                     {"buffer": len(buf), "dueling": getattr(learner, "dueling", True),
                      "successor": successor, "dropped_tail": dropped["tail"], "emitted": dropped["emitted"]})


class GreedyDQNPolicy:
    """Simulator policy: argmax of a numpy forward pass (R-L15), frozen normaliser."""

    def __init__(self, res: DQNResult, ctx: EvalContext):
        w = res.learner.export_weights()
        self.net = NumpyDuelingQ.from_weights(w, dueling=bool(res.diag.get("dueling", True)))
        self.tracker = FeatureTracker(ctx.trace.n_keys, ctx.cfg.features, ctx.predictor, res.norm)
        self.action_hist = np.zeros(N_ACTIONS, dtype=np.int64)

    def on_request(self, i, t, k, is_write, hit) -> None:
        self.tracker.on_request(i, t, k, is_write, hit)

    def decide(self, ctx) -> int:
        obs = self.tracker.observe(ctx, update_norm=False)
        a = int(np.argmax(self.net.q_values(obs)))
        self.action_hist[a] += 1
        return a


# ---- checkpoints (numpy-loadable; no torch needed to evaluate) ---------------------------------------
def save_checkpoint(path: str | Path, res: DQNResult, meta: dict | None = None) -> None:
    w = res.learner.export_weights()
    np.savez_compressed(
        path, **{f"w_{k}": v for k, v in w.items()},
        norm=np.frombuffer(json.dumps(res.norm.state_dict()).encode(), dtype=np.uint8),
        meta=np.frombuffer(json.dumps({"decisions": res.decisions, "gamma": res.gamma,
                                       "dueling": res.diag.get("dueling", True),
                                       **(meta or {})}).encode(), dtype=np.uint8))


def load_checkpoint(path: str | Path) -> tuple[dict, dict, dict]:
    z = np.load(path)
    w = {k[2:]: z[k] for k in z.files if k.startswith("w_")}
    norm = json.loads(bytes(z["norm"]).decode())
    meta = json.loads(bytes(z["meta"]).decode())
    return w, norm, meta
