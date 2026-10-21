"""Tabular Q-learning over a discretised 5-feature state (M8; R-L12, R-L13).

Frozen by docs/PREREGISTRATION.md (Addendum M8 and Amendment M8-a).  numpy only.

State: ``utilisation, hit_ratio, count_1000, volatility, predicted_ttl`` of the NORMALISED
observation, 4 bins each -> 1024 states x 45 actions.  The discretiser is fitted on a calibration
pass over the training slice and frozen.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from ..config import N_ACTIONS, TabularQConfig
from ..evaluation import EvalContext
from ..features import FeatureTracker, Normalizer
from ..features_spec import TABULAR_FEATURE_IDX
from ..runner import make_run


class Discretizer:
    """4 bins per feature.  ``qbin``: equal-frequency edges (fitted); ``ewidth``: equal-width on [0,1]."""

    def __init__(self, kind: str = "qbin", n_bins: int = 4, feat_idx=TABULAR_FEATURE_IDX):
        if kind not in ("qbin", "ewidth"):
            raise ValueError(kind)
        self.kind, self.n_bins, self.feat_idx = kind, n_bins, tuple(feat_idx)
        self.n_states = n_bins ** len(self.feat_idx)
        self.edges: list[np.ndarray] | None = None
        if kind == "ewidth":
            self.edges = [np.linspace(0.0, 1.0, n_bins + 1)[1:-1] for _ in self.feat_idx]

    def fit(self, obs: np.ndarray) -> "Discretizer":
        if self.kind == "ewidth":
            return self
        q = np.linspace(0, 1, self.n_bins + 1)[1:-1]
        self.edges = [np.quantile(obs[:, f], q) for f in self.feat_idx]
        return self

    def index(self, obs: np.ndarray) -> int:
        idx = 0
        for f, e in zip(self.feat_idx, self.edges):
            idx = idx * self.n_bins + int(np.searchsorted(e, obs[f], side="right"))
        return idx

    def index_many(self, obs: np.ndarray) -> np.ndarray:
        idx = np.zeros(len(obs), dtype=np.int64)
        for f, e in zip(self.feat_idx, self.edges):
            idx = idx * self.n_bins + np.searchsorted(e, obs[:, f], side="right")
        return idx


class TabularQ:
    def __init__(self, n_states: int, alpha: float, gamma: float, n_actions: int = N_ACTIONS,
                 min_visits_greedy: int = 1):
        self.Q = np.zeros((n_states, n_actions))
        self.n_sa = np.zeros((n_states, n_actions), dtype=np.int64)
        self.alpha, self.gamma, self.min_visits = alpha, gamma, min_visits_greedy
        self.default_action = 0
        self.n_updates = 0

    def update(self, s: int, a: int, r: float, s2: int) -> float:
        """Bellman update; returns the TD error."""
        td = r + self.gamma * self.Q[s2].max() - self.Q[s, a]
        self.Q[s, a] += self.alpha * td
        self.n_sa[s, a] += 1
        self.n_updates += 1
        return float(td)

    def act_train(self, s: int) -> int:
        return int(self.Q[s].argmax())

    def finalize(self) -> None:
        """Visit-weighted global-best action: the fallback for states never seen in training."""
        w = self.n_sa.sum(axis=0).astype(float)
        if w.sum() > 0:
            self.default_action = int(np.argmax((self.Q * self.n_sa).sum(axis=0) / np.maximum(w, 1)
                                                + np.where(w > 0, 0.0, -1e9)))

    def act_greedy(self, s: int) -> int:
        tried = self.n_sa[s] >= self.min_visits
        if not tried.any():
            return self.default_action
        return int(np.argmax(np.where(tried, self.Q[s], -np.inf)))

    def coverage(self) -> float:
        return float((self.n_sa.sum(axis=1) > 0).mean())


@dataclass
class TrainResult:
    agent: TabularQ
    disc: Discretizer
    norm: Normalizer
    decisions: int
    epochs: int
    td_abs_mean: float
    action_hist: np.ndarray
    kind: str
    gamma: float
    diag: dict = field(default_factory=dict)


class _Stop(Exception):
    pass


def eps_at(n: int, total: int, cfg: TabularQConfig) -> float:
    frac = min(1.0, n / max(cfg.eps_decay_frac * total, 1.0))
    return cfg.eps_start + frac * (cfg.eps - cfg.eps_start)


def train_tabular(ctx: EvalContext, kind: str = "qbin", gamma: float | None = None,
                  cfg: TabularQConfig | None = None, total_decisions: int | None = None) -> TrainResult:
    cfg = cfg or TabularQConfig()
    gamma = cfg.gamma if gamma is None else gamma
    total = cfg.total_decisions if total_decisions is None else total_decisions
    seed = ctx.seed
    rng = np.random.default_rng([seed, 17])
    a0, b0 = ctx.splits.train
    kw = dict(predictor=ctx.predictor, l1_capacity_bytes=ctx.l1_bytes, l2_capacity_bytes=ctx.l2_bytes)

    # ---- calibration pass (random:45, training slice only) ---------------------------------
    norm = Normalizer(ctx.cfg.features)
    cal_obs: list[np.ndarray] = []

    def cal_select(obs, c):
        cal_obs.append(obs.copy())
        return int(rng.integers(0, N_ACTIONS))

    make_run(ctx.trace, ctx.cfg, cal_select, normalizer=norm, learn_normalizer=True, seed=seed,
             **kw).go(a0, min(b0, a0 + cfg.calib_requests))
    norm.freeze()
    disc = Discretizer(kind, cfg.n_bins).fit(np.asarray(cal_obs))

    # ---- learning epochs (cold restart per replay of the training slice) ------------------------
    agent = TabularQ(disc.n_states, cfg.alpha, gamma, min_visits_greedy=cfg.min_visits_greedy)
    state = {"n": 0, "td": 0.0}
    hist = np.zeros(N_ACTIONS, dtype=np.int64)

    def select(obs, c):
        if state["n"] >= total:
            raise _Stop
        s = disc.index(obs)
        if rng.random() < eps_at(state["n"], total, cfg):
            a = int(rng.integers(0, N_ACTIONS))
        else:
            a = agent.act_train(s)
        state["n"] += 1
        hist[a] += 1
        return a

    def emit(tr):
        td = agent.update(disc.index(tr.s), tr.a, tr.r, disc.index(tr.s2))
        state["td"] += abs(td)

    epochs = 0
    while state["n"] < total:
        run = make_run(ctx.trace, ctx.cfg, select, normalizer=norm, learn_normalizer=False,
                       emit=emit, seed=seed * 1000 + epochs, **kw)
        try:
            run.go(a0, b0)
        except _Stop:
            pass
        epochs += 1
        if epochs > 200:
            raise RuntimeError("training slice yields too few decisions")
    agent.finalize()
    return TrainResult(agent, disc, norm, state["n"], epochs,
                       state["td"] / max(agent.n_updates, 1), hist, kind, gamma,
                       {"coverage_train": agent.coverage(), "updates": agent.n_updates})


class GreedyTabularPolicy:
    """Simulator policy: greedy w.r.t. a trained table, features from a frozen normaliser."""

    def __init__(self, res: TrainResult, ctx: EvalContext):
        self.res = res
        self.tracker = FeatureTracker(ctx.trace.n_keys, ctx.cfg.features, ctx.predictor, res.norm)
        self.states_seen = np.zeros(res.disc.n_states, dtype=np.int64)
        self.action_hist = np.zeros(N_ACTIONS, dtype=np.int64)

    def on_request(self, i, t, k, is_write, hit) -> None:
        self.tracker.on_request(i, t, k, is_write, hit)

    def decide(self, ctx) -> int:
        obs = self.tracker.observe(ctx, update_norm=False)
        s = self.res.disc.index(obs)
        self.states_seen[s] += 1
        a = self.res.agent.act_greedy(s)
        self.action_hist[a] += 1
        return a

    def unvisited_decision_share(self) -> float:
        n = self.states_seen.sum()
        if n == 0:
            return float("nan")
        unv = self.res.agent.n_sa.sum(axis=1) == 0
        return float(self.states_seen[unv].sum() / n)
