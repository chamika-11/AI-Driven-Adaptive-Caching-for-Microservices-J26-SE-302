import pathlib
p = pathlib.Path("scripts/dqn_cartpole.py"); s = p.read_text(encoding="utf-8")
def rep(a, b):
    global s
    assert s.count(a) == 1, a[:60]
    s = s.replace(a, b)
rep('''HP = dict(gamma=0.99, batch_size=128, buffer_size=50_000, learning_starts=1_000, train_every=2,
          eps_start=1.0, eps_end=0.05, eps_frac=0.30, tau=0.01)
LEARNER = dict(hidden=128, lr=5e-4, weight_decay=0.0, max_grad_norm=10.0)
''', '''# Presets fixed in docs/PREREGISTRATION.md, Amendment M9-b.  H1 FAILED gate C3 (1/5 seeds).
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
HP, LEARNER = PRESETS["H1"]
''')
rep('''def make_learner(backend, seed):
    kw = dict(obs_dim=4, n_actions=2, seed=seed, **LEARNER)''', '''def make_learner(backend, seed, learner=None):
    kw = dict(obs_dim=4, n_actions=2, seed=seed, **(learner or LEARNER))''')
rep('''    ap.add_argument("--sb3", action="store_true")
    a = ap.parse_args()
    scores = []''', '''    ap.add_argument("--sb3", action="store_true")
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
    scores = []''')
rep('''        learner = make_learner(a.backend, seed)
        curve = []''', '''        learner = make_learner(a.backend, seed, lk)
        curve = []''')
rep('''        train_on_env(gym.make("CartPole-v1"), learner, a.steps, seed=seed,
                     eval_hook=hook, eval_every=max(a.steps // 10, 1), **HP)''',
    '''        train_on_env(gym.make("CartPole-v1"), learner, a.steps, seed=seed,
                     eval_hook=hook, eval_every=max(a.steps // 10, 1), **hp)''')
rep('''def main():
    ap = argparse.ArgumentParser()''', '''def run_one(backend, seed, steps, preset):
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
    ap = argparse.ArgumentParser()''')
p.write_text(s, encoding="utf-8")
print("patched")
