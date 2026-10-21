"""PyTorch Double Dueling DQN learner (R-L1..R-L3).

WRITTEN on a machine where torch cannot be imported (C-47) and therefore executed only on
Colab.  It is checked against :class:`~rlcache.agents.qnet_numpy.NumpyDuelingQ` by
``tests/test_dqn_torch.py`` (pre-registered gate C1).  Import this module lazily: importing it
requires a working torch.

Same learner interface as the numpy reference:
``q_values(obs)``, ``train_step(batch, gamma)``, ``soft_update(tau)``, ``export_weights()``.
"""
from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


class QNet(nn.Module):
    """MLP body -> dueling heads.  ``Q = V + A - mean(A)`` (identifiability fix)."""

    def __init__(self, obs_dim: int = 19, n_actions: int = 45, hidden: int = 128,
                 dueling: bool = True):
        super().__init__()
        self.dueling = dueling
        self.fc1 = nn.Linear(obs_dim, hidden)
        self.fc2 = nn.Linear(hidden, hidden)
        self.adv = nn.Linear(hidden, n_actions)
        if dueling:
            self.val = nn.Linear(hidden, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        h = F.relu(self.fc2(F.relu(self.fc1(x))))
        a = self.adv(h)
        if not self.dueling:
            return a
        return self.val(h) + a - a.mean(dim=1, keepdim=True)


class TorchLearner:
    def __init__(self, obs_dim: int = 19, n_actions: int = 45, hidden: int = 128, seed: int = 0,
                 lr: float = 2.5e-4, weight_decay: float = 0.01, amsgrad: bool = True,
                 max_grad_norm: float = 10.0, dueling: bool = True, double: bool = True):
        torch.manual_seed(seed)
        torch.set_num_threads(1)
        self.device = torch.device("cpu")          # the net is far too small for a GPU to help
        self.net = QNet(obs_dim, n_actions, hidden, dueling).to(self.device)
        self.target = QNet(obs_dim, n_actions, hidden, dueling).to(self.device)
        self.target.load_state_dict(self.net.state_dict())
        for p in self.target.parameters():
            p.requires_grad_(False)
        self.opt = torch.optim.AdamW(self.net.parameters(), lr=lr, weight_decay=weight_decay,
                                     amsgrad=amsgrad)
        self.max_grad_norm, self.double, self.dueling = max_grad_norm, double, dueling
        self.n_actions = n_actions

    # ---- acting ------------------------------------------------------------------------------
    @torch.no_grad()
    def q_values(self, obs: np.ndarray) -> np.ndarray:
        x = torch.as_tensor(np.asarray(obs, dtype=np.float32)).unsqueeze(0)
        return self.net(x)[0].numpy()

    @torch.no_grad()
    def forward_np(self, X: np.ndarray, target: bool = False) -> np.ndarray:
        net = self.target if target else self.net
        return net(torch.as_tensor(np.asarray(X, dtype=np.float32))).numpy()

    # ---- learning ------------------------------------------------------------------------------
    def _tensors(self, batch: dict):
        t = lambda a, dt: torch.as_tensor(np.asarray(a), dtype=dt)          # noqa: E731
        return (t(batch["obs"], torch.float32), t(batch["actions"], torch.int64),
                t(batch["rewards"], torch.float32), t(batch["next_obs"], torch.float32),
                t(batch["dones"], torch.float32))

    def loss_and_grads(self, batch: dict, gamma: float):
        """Loss and per-parameter gradients WITHOUT stepping (used by the C1 equivalence test)."""
        obs, act, rew, nxt, done = self._tensors(batch)
        q_sa = self.net(obs).gather(1, act.unsqueeze(1)).squeeze(1)          # (B,) not (B, B)
        with torch.no_grad():                                               # whole target graph-free
            if self.double:
                a_star = self.net(nxt).argmax(dim=1, keepdim=True)          # online picks ...
                q_next = self.target(nxt).gather(1, a_star).squeeze(1)      # ... target evaluates
            else:
                q_next = self.target(nxt).max(dim=1).values
            target = rew + gamma * (1.0 - done) * q_next
        assert q_sa.shape == target.shape
        loss = F.smooth_l1_loss(q_sa, target)
        self.opt.zero_grad(set_to_none=True)
        loss.backward()
        metrics = {"loss": float(loss.item()), "q_mean": float(q_sa.mean().item()),
                   "q_max": float(q_sa.max().item()), "target_mean": float(target.mean().item())}
        return loss, {n: p.grad.detach().clone() for n, p in self.net.named_parameters()}, metrics

    def train_step(self, batch: dict, gamma: float) -> dict:
        _, _, metrics = self.loss_and_grads(batch, gamma)                   # leaves .grad populated
        gn = torch.nn.utils.clip_grad_norm_(self.net.parameters(), self.max_grad_norm)
        self.opt.step()
        metrics["grad_norm"] = float(gn)
        return metrics

    @torch.no_grad()
    def soft_update(self, tau: float) -> None:
        for p, tp in zip(self.net.parameters(), self.target.parameters()):
            tp.mul_(1.0 - tau).add_(tau * p)

    @torch.no_grad()
    def sync_target(self) -> None:
        """Hard copy online -> target (tau = 1); used by the published CartPole recipe."""
        self.target.load_state_dict(self.net.state_dict())

    # ---- weights (numpy layout (in, out), same names as the reference) ---------------------------
    def export_weights(self) -> dict[str, np.ndarray]:
        g = lambda m: m.weight.detach().numpy().T.copy()                   # noqa: E731
        b = lambda m: m.bias.detach().numpy().copy()                       # noqa: E731
        w = {"W1": g(self.net.fc1), "b1": b(self.net.fc1), "W2": g(self.net.fc2),
             "b2": b(self.net.fc2), "Wa": g(self.net.adv), "ba": b(self.net.adv)}
        if self.dueling:
            w["Wv"], w["bv"] = g(self.net.val), b(self.net.val)
        return w

    @torch.no_grad()
    def load_weights(self, w: dict, target: bool = True) -> None:
        def put(m, W, bias):
            m.weight.copy_(torch.as_tensor(np.asarray(w[W], np.float32).T))
            m.bias.copy_(torch.as_tensor(np.asarray(w[bias], np.float32)))
        put(self.net.fc1, "W1", "b1")
        put(self.net.fc2, "W2", "b2")
        put(self.net.adv, "Wa", "ba")
        if self.dueling:
            put(self.net.val, "Wv", "bv")
        if target:
            self.target.load_state_dict(self.net.state_dict())

    # name map: torch parameter name -> numpy reference parameter name (and transpose flag)
    GRAD_MAP = {"fc1.weight": ("W1", True), "fc1.bias": ("b1", False),
                "fc2.weight": ("W2", True), "fc2.bias": ("b2", False),
                "adv.weight": ("Wa", True), "adv.bias": ("ba", False),
                "val.weight": ("Wv", True), "val.bias": ("bv", False)}
