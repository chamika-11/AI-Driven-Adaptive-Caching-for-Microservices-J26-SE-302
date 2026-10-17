"""Pure-numpy dueling Q-network with manual backprop (reference learner + inference path).

Three jobs:
1. the numerical REFERENCE the PyTorch learner is checked against on Colab (gate C1);
2. a slow but working learner so the training driver and probes can be tested where torch cannot
   be imported (C-47);
3. the numpy-only inference path from exported weights (R-L15).

Formulas follow torch exactly so trajectories are comparable: Linear init U(+-1/sqrt(fan_in)),
AdamW with decoupled weight decay and amsgrad as in ``torch.optim.AdamW``, Huber (smooth L1,
beta = 1) loss averaged over the batch, global gradient-norm clipping, soft target update.

Weights are stored as ``W`` of shape (in, out) (torch's ``Linear.weight`` is (out, in)).
"""
from __future__ import annotations

import numpy as np

PARAM_NAMES_DUELING = ("W1", "b1", "W2", "b2", "Wv", "bv", "Wa", "ba")
PARAM_NAMES_PLAIN = ("W1", "b1", "W2", "b2", "Wa", "ba")


def _init(rng, fan_in, shape, dtype):
    bound = 1.0 / np.sqrt(fan_in)
    return rng.uniform(-bound, bound, shape).astype(dtype)


class NumpyDuelingQ:
    def __init__(self, obs_dim: int = 19, n_actions: int = 45, hidden: int = 128, seed: int = 0,
                 lr: float = 2.5e-4, weight_decay: float = 0.01, amsgrad: bool = True,
                 max_grad_norm: float = 10.0, dueling: bool = True, double: bool = True,
                 dtype=np.float32, betas=(0.9, 0.999), eps: float = 1e-8):
        self.obs_dim, self.n_actions, self.hidden = obs_dim, n_actions, hidden
        self.dueling, self.double, self.dtype = dueling, double, dtype
        self.lr, self.wd, self.amsgrad = lr, weight_decay, amsgrad
        self.max_grad_norm, self.betas, self.eps = max_grad_norm, betas, eps
        rng = np.random.default_rng(seed)
        p = {
            "W1": _init(rng, obs_dim, (obs_dim, hidden), dtype), "b1": _init(rng, obs_dim, (hidden,), dtype),
            "W2": _init(rng, hidden, (hidden, hidden), dtype), "b2": _init(rng, hidden, (hidden,), dtype),
            "Wa": _init(rng, hidden, (hidden, n_actions), dtype), "ba": _init(rng, hidden, (n_actions,), dtype),
        }
        if dueling:
            p["Wv"] = _init(rng, hidden, (hidden, 1), dtype)
            p["bv"] = _init(rng, hidden, (1,), dtype)
        self.params = p
        self.target = {k: v.copy() for k, v in p.items()}
        self._m = {k: np.zeros_like(v) for k, v in p.items()}
        self._v = {k: np.zeros_like(v) for k, v in p.items()}
        self._vmax = {k: np.zeros_like(v) for k, v in p.items()}
        self.t = 0

    # ---- forward -----------------------------------------------------------------------------
    @staticmethod
    def _forward(p: dict, X: np.ndarray, dueling: bool):
        h1 = np.maximum(X @ p["W1"] + p["b1"], 0.0)
        h2 = np.maximum(h1 @ p["W2"] + p["b2"], 0.0)
        a = h2 @ p["Wa"] + p["ba"]
        if dueling:
            v = h2 @ p["Wv"] + p["bv"]
            q = v + a - a.mean(axis=1, keepdims=True)
        else:
            q = a
        return q, (X, h1, h2)

    def forward(self, X: np.ndarray, target: bool = False) -> np.ndarray:
        return self._forward(self.target if target else self.params,
                             np.asarray(X, dtype=self.dtype), self.dueling)[0]

    def q_values(self, obs: np.ndarray) -> np.ndarray:
        return self.forward(np.asarray(obs, dtype=self.dtype)[None, :])[0]

    # ---- loss and gradients ---------------------------------------------------------------------
    def td_targets(self, batch: dict, gamma: float) -> np.ndarray:
        nxt = np.asarray(batch["next_obs"], dtype=self.dtype)
        q_t = self.forward(nxt, target=True)
        if self.double:
            a_star = self.forward(nxt).argmax(axis=1)             # ONLINE net picks ...
            q_next = q_t[np.arange(len(a_star)), a_star]          # ... TARGET net evaluates
        else:
            q_next = q_t.max(axis=1)
        r = np.asarray(batch["rewards"], dtype=self.dtype)
        d = np.asarray(batch["dones"], dtype=self.dtype)
        return r + gamma * (1.0 - d) * q_next

    def loss_and_grads(self, batch: dict, gamma: float):
        X = np.asarray(batch["obs"], dtype=self.dtype)
        a = np.asarray(batch["actions"], dtype=np.int64)
        B = len(a)
        target = self.td_targets(batch, gamma)
        q, (_, h1, h2) = self._forward(self.params, X, self.dueling)
        idx = np.arange(B)
        td = q[idx, a] - target
        absd = np.abs(td)
        loss = float(np.where(absd < 1.0, 0.5 * td * td, absd - 0.5).mean())
        dq = np.zeros_like(q)
        dq[idx, a] = np.clip(td, -1.0, 1.0) / B                   # d Huber / d q_sa, mean over batch
        p, g = self.params, {}
        if self.dueling:
            dv = dq.sum(axis=1, keepdims=True)
            da = dq - dq.mean(axis=1, keepdims=True)
            g["Wv"], g["bv"] = h2.T @ dv, dv.sum(axis=0)
            dh2 = dv @ p["Wv"].T + da @ p["Wa"].T
        else:
            da = dq
            dh2 = da @ p["Wa"].T
        g["Wa"], g["ba"] = h2.T @ da, da.sum(axis=0)
        dz2 = dh2 * (h2 > 0)
        g["W2"], g["b2"] = h1.T @ dz2, dz2.sum(axis=0)
        dz1 = (dz2 @ p["W2"].T) * (h1 > 0)
        g["W1"], g["b1"] = X.T @ dz1, dz1.sum(axis=0)
        metrics = {"loss": loss, "q_mean": float(q[idx, a].mean()), "q_max": float(q[idx, a].max()),
                   "target_mean": float(target.mean())}
        return loss, g, metrics

    # ---- optimiser (torch.optim.AdamW formulas) -------------------------------------------------
    def apply_adamw(self, grads: dict) -> float:
        total = float(np.sqrt(sum(float((g.astype(np.float64) ** 2).sum()) for g in grads.values())))
        if self.max_grad_norm and total > self.max_grad_norm:
            scale = self.max_grad_norm / (total + 1e-6)           # torch.nn.utils.clip_grad_norm_
            grads = {k: g * scale for k, g in grads.items()}
        self.t += 1
        b1, b2 = self.betas
        bc1, bc2 = 1.0 - b1 ** self.t, 1.0 - b2 ** self.t
        for k, p in self.params.items():
            g = grads[k]
            p *= (1.0 - self.lr * self.wd)                       # decoupled weight decay
            self._m[k] = b1 * self._m[k] + (1.0 - b1) * g
            self._v[k] = b2 * self._v[k] + (1.0 - b2) * g * g
            if self.amsgrad:
                self._vmax[k] = np.maximum(self._vmax[k], self._v[k])
                denom = np.sqrt(self._vmax[k]) / np.sqrt(bc2) + self.eps
            else:
                denom = np.sqrt(self._v[k]) / np.sqrt(bc2) + self.eps
            p -= (self.lr / bc1) * self._m[k] / denom
        return total

    def train_step(self, batch: dict, gamma: float) -> dict:
        loss, grads, metrics = self.loss_and_grads(batch, gamma)
        metrics["grad_norm"] = self.apply_adamw(grads)
        return metrics

    def soft_update(self, tau: float) -> None:
        for k in self.params:
            self.target[k] = (1.0 - tau) * self.target[k] + tau * self.params[k]

    def sync_target(self) -> None:
        self.target = {k: v.copy() for k, v in self.params.items()}

    # ---- weights I/O ----------------------------------------------------------------------------------
    def export_weights(self) -> dict[str, np.ndarray]:
        return {k: v.astype(np.float32).copy() for k, v in self.params.items()}

    def load_weights(self, w: dict, target: bool = True) -> None:
        for k in self.params:
            self.params[k] = np.asarray(w[k], dtype=self.dtype).copy()
        if target:
            self.sync_target()

    @classmethod
    def from_weights(cls, w: dict, dueling: bool = True, **kw) -> "NumpyDuelingQ":
        hidden = w["W1"].shape[1]
        net = cls(obs_dim=w["W1"].shape[0], n_actions=w["Wa"].shape[1], hidden=hidden,
                  dueling=dueling, **kw)
        net.load_weights(w)
        return net
