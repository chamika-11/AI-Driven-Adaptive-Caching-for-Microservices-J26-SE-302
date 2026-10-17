"""Gymnasium adapter over the event-driven engine (R-S17, D-2).

This is a THIN API-hygiene wrapper (``check_env``, SB3 cross-checks).  The engine is the source
of truth.  Semantics that differ from a textbook Gym task, on purpose:

* one ``step`` = one placement decision (a cache miss), not one request;
* the returned ``reward`` is the sum of clipped rewards of the insertions that CLOSED since the
  previous step -- an accounting signal, NOT the credit for the action just given (that reward
  arrives later; learning code must use :class:`~rlcache.transitions.TransitionAssembler`);
* ``terminated`` is always False (continuing task); ``truncated`` is True when the slice ends.
"""
from __future__ import annotations

from typing import Any, Optional

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from .config import N_ACTIONS, N_FEATURES, Config
from .features import FeatureTracker, Normalizer
from .features_spec import FEATURE_INDEX
from .predictor.standin import PredictorTables
from .reward import compute_reward
from .sim.engine import R_TRUNC, Simulator, resolve_capacities
from .trace.record import Trace

_UTIL = FEATURE_INDEX["utilisation"]


class _EnvPolicy:
    """Receives closures; never asked to decide (the env commits actions itself)."""

    def __init__(self, env: "CacheEnv"):
        self.env = env

    def decide(self, ctx) -> int:                      # pragma: no cover - not used
        raise RuntimeError("CacheEnv commits actions itself")

    def on_decision(self, ins) -> None:
        ins.payload = self.env._util_at_decision

    def on_close(self, ins) -> None:
        if ins.close_reason == R_TRUNC or ins.payload is None:
            return
        parts = compute_reward(ins, self.env.cfg.reward, self.env._cap_total, ins.payload)
        self.env._acc += parts.clipped
        self.env._n_closed_step += 1


class CacheEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, trace: Trace, cfg: Optional[Config] = None,
                 predictor: Optional[PredictorTables] = None, start: int = 0,
                 end: Optional[int] = None, seed: int = 0):
        super().__init__()
        self.trace, self.cfg = trace, cfg or Config()
        self.predictor = predictor
        self.start, self.end = start, len(trace) if end is None else end
        self._seed = seed
        self.action_space = spaces.Discrete(N_ACTIONS)
        self.observation_space = spaces.Box(-1.0, 1.0, (N_FEATURES,), np.float32)
        self.sim: Simulator | None = None
        self._last_obs = np.zeros(N_FEATURES, np.float32)

    def reset(self, *, seed: Optional[int] = None, options: Optional[dict] = None):
        super().reset(seed=seed)
        if seed is not None:
            self._seed = int(seed)
        l1, l2 = resolve_capacities(self.trace, self.cfg.cache)
        self._cap_total = float(l1 + l2)
        self.tracker = FeatureTracker(self.trace.n_keys, self.cfg.features, self.predictor,
                                      Normalizer(self.cfg.features))
        self._acc = 0.0
        self._n_closed_step = 0
        self._util_at_decision = 0.0
        self.sim = Simulator(self.trace, self.cfg, _EnvPolicy(self), l1_capacity_bytes=l1,
                             l2_capacity_bytes=l2, seed=self._seed, observer=self.tracker,
                             keep_closed=False, record_latencies=False)
        self.sim.begin(self.start, self.end)
        ctx = self.sim.next_decision()
        self._ctx = ctx
        if ctx is None:
            return self._last_obs.copy(), {"empty": True}
        self._last_obs = self._observe(ctx)
        return self._last_obs.copy(), {"idx": ctx.idx, "key": ctx.key}

    def _observe(self, ctx) -> np.ndarray:
        obs = self.tracker.observe(ctx, update_norm=True)
        self._util_at_decision = float(obs[_UTIL])
        return obs

    def step(self, action: int):
        if self.sim is None or self._ctx is None:
            raise RuntimeError("call reset() first")
        self._acc = 0.0
        self._n_closed_step = 0
        self.sim.commit(int(action))
        ctx = self.sim.next_decision()
        reward = float(self._acc)
        info: dict[str, Any] = {"n_closed": self._n_closed_step, "t": self.sim.now}
        if ctx is None:
            self._ctx = None
            return self._last_obs.copy(), reward, False, True, info
        self._ctx = ctx
        self._last_obs = self._observe(ctx)
        info.update(idx=ctx.idx, key=ctx.key)
        return self._last_obs.copy(), reward, False, False, info
