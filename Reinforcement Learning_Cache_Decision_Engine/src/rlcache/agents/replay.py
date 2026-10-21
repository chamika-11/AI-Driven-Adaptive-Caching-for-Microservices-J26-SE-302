"""numpy ring-buffer replay (R-L4): float32 storage, its OWN seeded RNG, no torch dependency."""
from __future__ import annotations

import numpy as np


class ReplayBuffer:
    def __init__(self, capacity: int, obs_dim: int, seed: int = 0):
        self.capacity = int(capacity)
        self.obs = np.zeros((capacity, obs_dim), dtype=np.float32)
        self.next_obs = np.zeros((capacity, obs_dim), dtype=np.float32)
        self.actions = np.zeros(capacity, dtype=np.int64)
        self.rewards = np.zeros(capacity, dtype=np.float32)
        self.dones = np.zeros(capacity, dtype=np.float32)      # float: used in arithmetic
        self.ptr = 0
        self.size = 0
        self.rng = np.random.default_rng(seed)

    def add(self, obs, action, reward, next_obs, done) -> None:
        i = self.ptr
        self.obs[i] = obs
        self.next_obs[i] = next_obs
        self.actions[i] = action
        self.rewards[i] = reward
        self.dones[i] = float(done)
        self.ptr = (self.ptr + 1) % self.capacity
        self.size = min(self.size + 1, self.capacity)

    def sample(self, batch_size: int) -> dict[str, np.ndarray]:
        if self.size == 0:
            raise ValueError("empty buffer")
        idx = self.rng.integers(0, self.size, size=batch_size)
        return {"obs": self.obs[idx], "actions": self.actions[idx], "rewards": self.rewards[idx],
                "next_obs": self.next_obs[idx], "dones": self.dones[idx]}

    def __len__(self) -> int:
        return self.size
