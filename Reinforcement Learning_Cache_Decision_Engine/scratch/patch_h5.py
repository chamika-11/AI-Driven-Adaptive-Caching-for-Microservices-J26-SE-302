import pathlib


def edit(path, pairs):
    p = pathlib.Path(path)
    s = p.read_text(encoding="utf-8")
    for a, b in pairs:
        assert s.count(a) == 1, (path, a[:70])
        s = s.replace(a, b)
    p.write_text(s, encoding="utf-8")


edit("src/rlcache/agents/dqn_torch.py", [(
    '''    # ---- weights (numpy layout (in, out), same names as the reference) ---------------------------''',
    '''    @torch.no_grad()
    def sync_target(self) -> None:
        """Hard copy online -> target (tau = 1); used by the published CartPole recipe."""
        self.target.load_state_dict(self.net.state_dict())

    # ---- weights (numpy layout (in, out), same names as the reference) ---------------------------''')])

edit("src/rlcache/agents/probes.py", [
    ('''def train_on_env(env, learner, steps: int, gamma: float, batch_size: int = 64,
                 buffer_size: int = 20_000, learning_starts: int = 200, train_every: int = 1,
                 eps_start: float = 1.0, eps_end: float = 0.1, eps_frac: float = 0.5, tau: float = 0.01,
                 seed: int = 0, eval_hook=None, eval_every: int = 0):
    """Plain online DQN loop for small episodic gym tasks (probes, CartPole)."""''',
     '''def train_on_env(env, learner, steps: int, gamma: float, batch_size: int = 64,
                 buffer_size: int = 20_000, learning_starts: int = 200, train_every: int = 1,
                 eps_start: float = 1.0, eps_end: float = 0.1, eps_frac: float = 0.5, tau: float = 0.01,
                 seed: int = 0, eval_hook=None, eval_every: int = 0, grad_steps: int = 1,
                 target_update_interval: int | None = None):
    """Plain online DQN loop for small episodic gym tasks (probes, CartPole).

    Every ``train_every`` environment steps (once ``learning_starts`` is reached) it performs a burst
    of ``grad_steps`` gradient steps.  Target update: a soft update of rate ``tau`` after every
    gradient step, OR (if ``target_update_interval`` is set) a hard copy every that many
    environment steps (the RL-Zoo CartPole recipe: train_freq 256, gradient_steps 128, interval 10).
    """'''),
    ('''        if step >= learning_starts and step % train_every == 0 and len(buf) >= batch_size:
            learner.train_step(buf.sample(batch_size), gamma)
            learner.soft_update(tau)''',
     '''        if step >= learning_starts and step % train_every == 0 and len(buf) >= batch_size:
            for _ in range(grad_steps):
                learner.train_step(buf.sample(batch_size), gamma)
                if target_update_interval is None:
                    learner.soft_update(tau)
        if target_update_interval is not None and (step + 1) % target_update_interval == 0:
            learner.sync_target()'''),
])

edit("scripts/dqn_cartpole.py", [
    ('''HP, LEARNER = PRESETS["H1"]
''', '''# H5: RL-Baselines3-Zoo CartPole-v1 DQN recipe (Amendment M9-c), as implemented in this learner.
# train_freq 256 + gradient_steps 128, hard target copy every 10 env steps, net 256x256.
_H5_HP = dict(gamma=0.99, batch_size=64, buffer_size=100_000, learning_starts=1_000, train_every=256,
              grad_steps=128, target_update_interval=10, eps_start=1.0, eps_end=0.04, eps_frac=0.16)
_H5_LK = dict(hidden=256, lr=2.3e-3, weight_decay=0.0, max_grad_norm=10.0)
PRESETS["H5"] = (_H5_HP, {**_H5_LK, "dueling": True, "double": True})
PRESETS["H5v"] = (_H5_HP, {**_H5_LK, "dueling": False, "double": False})   # non-gating diagnostic
HP, LEARNER = PRESETS["H1"]
'''),
])
print("patched")
