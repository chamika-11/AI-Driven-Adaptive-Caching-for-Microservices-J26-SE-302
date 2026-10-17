"""Gate C3: hand-written DQN on CartPole-v1 (checks the learner, not the cache problem).

    python scripts/dqn_cartpole.py --backend torch --seeds 0 1 2 3 4 --steps 100000

Pre-registered (Addendum M9): mean greedy return over the final 10 evaluation episodes >= 300 in
at least 3 of 5 seeds.  CartPole hyper-parameters are its own and are not reused for the cache.
Optional: --sb3 also trains a Stable-Baselines3 DQN for a rough comparison (not gating).
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import gymnasium as gym  # noqa: E402
import numpy as np  # noqa: E402

from rlcache.agents.probes import train_on_env  # noqa: E402
from rlcache.agents.qnet_numpy import NumpyDuelingQ  # noqa: E402

# Presets fixed in docs/PREREGISTRATION.md, Amendment M9-b.  H1 FAILED gate C3 (1/5 seeds).
_BASE = dict(gamma=0.99, batch_size=128, buffer_size=50_000, learning_starts=1_000, train_every=2,
             eps_start=1.0, eps_end=0.05, eps_frac=0.30, tau=0.01)
PRESETS = {
    "H1": (_BASE, dict(hidden=128, lr=5e-4, weight_decay=0.0, max_grad_norm=10.0)),
    "H2": ({**_BASE, "tau": 0.005, "train_every": 4}, dict(hidden=128, lr=2.5e-4, weight_decay=0.0,
                                                           max_grad_norm=10.0)),
    "H3": ({**_BASE, "tau": 0.005, "train_every": 1, "batch_size": 64},
           dict(hidden=128, lr=2.5e-4, weight_decay=0.0, max_grad_norm=10.0)),
    "H4": ({**_BASE, "tau": 0.005, "train_every": 4, "learning_starts": 5_000, "eps_frac": 0.50},
           dict(hidden=128, lr=2.5e-4, weight_decay=0.0, max_grad_norm=10.0)),
}
# H5: RL-Baselines3-Zoo CartPole-v1 DQN recipe (Amendment M9-c), as implemented in this learner.
# train_freq 256 + gradient_steps 128, hard target copy every 10 env steps, net 256x256.
_H5_HP = dict(gamma=0.99, batch_size=64, buffer_size=100_000, learning_starts=1_000, train_every=256,
              grad_steps=128, target_update_interval=10, eps_start=1.0, eps_end=0.04, eps_frac=0.16)
_H5_LK = dict(hidden=256, lr=2.3e-3, weight_decay=0.0, max_grad_norm=10.0)
PRESETS["H5"] = (_H5_HP, {**_H5_LK, "dueling": True, "double": True})
PRESETS["H5v"] = (_H5_HP, {**_H5_LK, "dueling": False, "double": False})   # non-gating diagnostic
HP, LEARNER = PRESETS["H1"]


def make_learner(backend, seed, learner=None):
    kw = dict(obs_dim=4, n_actions=2, seed=seed, **(learner or LEARNER))
    if backend == "torch":
        from rlcache.agents.dqn_torch import TorchLearner
        return TorchLearner(**kw)
    return NumpyDuelingQ(**kw)


def greedy_return(learner, episodes=10, seed=1000):
    env = gym.make("CartPole-v1")
    out = []
    for e in range(episodes):
        obs, _ = env.reset(seed=seed + e)
        done, total = False, 0.0
        while not done:
            a = int(np.argmax(learner.q_values(obs)))
            obs, r, term, trunc, _ = env.step(a)
            total += r
            done = term or trunc
        out.append(total)
    return float(np.mean(out))


def run_one(backend, seed, steps, preset):
    hp, lk = PRESETS[preset]
    t0 = time.time()
    learner = make_learner(backend, seed, lk)
    curve = []

    def hook(step, lr_, returns):
        curve.append(greedy_return(lr_, 3, seed=5000 + step))

    train_on_env(gym.make("CartPole-v1"), learner, steps, seed=seed, eval_hook=hook,
                 eval_every=max(steps // 10, 1), **hp)
    return seed, greedy_return(learner, 10), curve, time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=("torch", "numpy"), default="torch")
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2, 3, 4])
    ap.add_argument("--steps", type=int, default=100_000)
    ap.add_argument("--sb3", action="store_true")
    ap.add_argument("--preset", choices=sorted(PRESETS), default="H1")
    ap.add_argument("--procs", type=int, default=1, help="parallel seeds")
    a = ap.parse_args()
    hp, lk = PRESETS[a.preset]
    print(f"preset {a.preset}: {hp} | learner {lk}", flush=True)
    if a.procs > 1:
        import multiprocessing as mp
        with mp.get_context("spawn").Pool(a.procs) as pool:
            res = pool.starmap(run_one, [(a.backend, s, a.steps, a.preset) for s in a.seeds])
        for seed, final, curve, secs in res:
            print(f"seed {seed}: final greedy return {final:6.1f}   curve "
                  + " ".join(f"{c:.0f}" for c in curve) + f"   ({secs:.0f}s)")
        scores = [r[1] for r in res]
        n_ok = sum(x >= 300 for x in scores)
        print(f"\nmean final return {np.mean(scores):.1f}; seeds >= 300: {n_ok}/{len(scores)} "
              f"(gate C3 needs >= 3 of 5 on seeds 0-4)")
        return 0 if n_ok >= 3 else 1
    scores = []
    for seed in a.seeds:
        t0 = time.time()
        learner = make_learner(a.backend, seed, lk)
        curve = []

        def hook(step, lr_, returns, curve=curve):
            curve.append((step, greedy_return(lr_, 3, seed=5000 + step)))

        train_on_env(gym.make("CartPole-v1"), learner, a.steps, seed=seed,
                     eval_hook=hook, eval_every=max(a.steps // 10, 1), **hp)
        final = greedy_return(learner, 10)
        scores.append(final)
        print(f"seed {seed}: final greedy return {final:6.1f}   curve "
              + " ".join(f"{c[1]:.0f}" for c in curve) + f"   ({time.time()-t0:.0f}s)", flush=True)
    n_ok = sum(s >= 300 for s in scores)
    print(f"\nseeds with mean return >= 300: {n_ok}/{len(scores)}  (gate C3 needs >= 3 of 5)")
    if a.sb3:
        try:
            from stable_baselines3 import DQN
            sb = []
            for seed in a.seeds[:3]:
                m = DQN("MlpPolicy", gym.make("CartPole-v1"), seed=seed, verbose=0)
                m.learn(a.steps)
                env, tot = gym.make("CartPole-v1"), []
                for e in range(10):
                    o, _ = env.reset(seed=9000 + e)
                    d, g = False, 0.0
                    while not d:
                        act, _ = m.predict(o, deterministic=True)
                        o, r, te, tr, _ = env.step(int(act))
                        g += r
                        d = te or tr
                    tot.append(g)
                sb.append(float(np.mean(tot)))
            print("SB3 DQN (default hyper-parameters, for context only):", [round(x) for x in sb])
        except ImportError:
            print("stable-baselines3 not installed; skipping the comparison")
    return 0 if n_ok >= 3 else 1


if __name__ == "__main__":
    sys.exit(main())
