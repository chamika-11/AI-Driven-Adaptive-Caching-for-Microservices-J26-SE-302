"""Probe environments (Andy Jones, 'Debugging RL') and a generic gym training loop.

Each probe isolates one part of the learner and has hand-computable Q-values (Addendum M9, gate
C2).  Own definitions: the MD's probe 3 reuses observation 0 on both steps, which ALIASES the
two states, so here the second observation is distinct.

numpy + gymnasium only.
"""
from __future__ import annotations

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from .replay import ReplayBuffer


class Probe(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, variant: int = 1):
        super().__init__()
        assert variant in (1, 2, 3, 4, 5)
        self.variant = variant
        self.observation_space = spaces.Box(-1.0, 1.0, (1,), np.float32)
        self.action_space = spaces.Discrete(2 if variant in (4, 5) else 1)
        self.t, self.o = 0, 0.0

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.t = 0
        self.o = float(self.np_random.choice([-1.0, 1.0])) if self.variant in (2, 5) else 0.0
        return np.array([self.o], np.float32), {}

    def step(self, a):
        v = self.variant
        if v == 1:
            r, done = 1.0, True
        elif v == 2:
            r, done = self.o, True
        elif v == 3:
            self.t += 1
            if self.t == 1:
                self.o = 1.0                      # distinct second observation
                return np.array([1.0], np.float32), 0.0, False, False, {}
            r, done = 1.0, True
        elif v == 4:
            r, done = (-1.0 if int(a) == 0 else 1.0), True
        else:
            r, done = (1.0 if int(a) == int(self.o > 0) else -1.0), True
        return np.array([self.o], np.float32), r, done, False, {}


def expected_q(variant: int, gamma: float) -> dict[tuple[float, ...], list[float]]:
    """Hand-computed optimal Q for each observation (key: the observation tuple)."""
    return {
        1: {(0.0,): [1.0]},
        2: {(1.0,): [1.0], (-1.0,): [-1.0]},
        3: {(0.0,): [gamma], (1.0,): [1.0]},
        4: {(0.0,): [-1.0, 1.0]},
        5: {(1.0,): [-1.0, 1.0], (-1.0,): [1.0, -1.0]},
    }[variant]


def train_on_env(env, learner, steps: int, gamma: float, batch_size: int = 64,
                 buffer_size: int = 20_000, learning_starts: int = 200, train_every: int = 1,
                 eps_start: float = 1.0, eps_end: float = 0.1, eps_frac: float = 0.5, tau: float = 0.01,
                 seed: int = 0, eval_hook=None, eval_every: int = 0, grad_steps: int = 1,
                 target_update_interval: int | None = None):
    """Plain online DQN loop for small episodic gym tasks (probes, CartPole).

    Every ``train_every`` environment steps (once ``learning_starts`` is reached) it performs a burst
    of ``grad_steps`` gradient steps.  Target update: a soft update of rate ``tau`` after every
    gradient step, OR (if ``target_update_interval`` is set) a hard copy every that many
    environment steps (the RL-Zoo CartPole recipe: train_freq 256, gradient_steps 128, interval 10).
    """
    obs_dim = env.observation_space.shape[0]
    n_actions = env.action_space.n
    buf = ReplayBuffer(buffer_size, obs_dim, seed=seed)
    rng = np.random.default_rng(seed)
    obs, _ = env.reset(seed=seed)
    ep_ret, returns = 0.0, []
    for step in range(steps):
        eps = eps_start + min(1.0, step / max(eps_frac * steps, 1)) * (eps_end - eps_start)
        if rng.random() < eps:
            a = int(rng.integers(0, n_actions))
        else:
            a = int(np.argmax(learner.q_values(obs)))
        nxt, r, term, trunc, _ = env.step(a)
        # bootstrap THROUGH truncation; cut only on true termination
        buf.add(obs, a, r, nxt, term)
        ep_ret += r
        obs = nxt
        if term or trunc:
            returns.append(ep_ret)
            ep_ret = 0.0
            obs, _ = env.reset()
        if step >= learning_starts and step % train_every == 0 and len(buf) >= batch_size:
            for _ in range(grad_steps):
                learner.train_step(buf.sample(batch_size), gamma)
                if target_update_interval is None:
                    learner.soft_update(tau)
        if target_update_interval is not None and (step + 1) % target_update_interval == 0:
            learner.sync_target()
        if eval_hook is not None and eval_every and (step + 1) % eval_every == 0:
            eval_hook(step + 1, learner, returns)
    return returns
