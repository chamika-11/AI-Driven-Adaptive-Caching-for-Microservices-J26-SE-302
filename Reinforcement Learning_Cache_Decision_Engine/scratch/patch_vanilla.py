import pathlib
p = pathlib.Path("scripts/run_dqn.py"); s = p.read_text(encoding="utf-8")
def rep(a, b):
    global s
    assert s.count(a) == 1, a[:70]
    s = s.replace(a, b)
rep('VARIANTS = {"dqn": 0.95, "dqn_bandit": 0.0}',
    '''VARIANTS = {"dqn": 0.95, "dqn_bandit": 0.0, "dqn_vanilla": 0.95}      # Amendment M9-d
# architecture flags per variant: (dueling, double).  dqn_vanilla is the ablation arm.
ARCH = {"dqn": (True, True), "dqn_bandit": (True, True), "dqn_vanilla": (False, False)}''')
rep('''def make_learner(backend: str, seed: int):
    from rlcache.config import DQNConfig
    c = DQNConfig()
    kw = dict(obs_dim=19, n_actions=45, hidden=c.hidden, seed=seed, lr=c.lr, dueling=c.dueling,
              double=c.double, max_grad_norm=c.max_grad_norm)''',
    '''def make_learner(backend: str, seed: int, variant: str = "dqn"):
    from rlcache.config import DQNConfig
    c = DQNConfig()
    dueling, double = ARCH[variant]
    kw = dict(obs_dim=19, n_actions=45, hidden=c.hidden, seed=seed, lr=c.lr, dueling=dueling,
              double=double, max_grad_norm=c.max_grad_norm)''')
rep("    res = T.train_dqn(ctx, make_learner(backend, ctx.seed), cfg, gamma=gamma,",
    "    res = T.train_dqn(ctx, make_learner(backend, ctx.seed, variant), cfg, gamma=gamma,")
rep('''        spec = Spec(f"dqn:{variant[4:] or 'main'}" if variant != "dqn" else "dqn:main", "dqn", "learned",
                    lambda c, p=pol: p)''', '''        spec = Spec("dqn:main" if variant == "dqn" else f"dqn:{variant[4:]}", "dqn", "learned",
                    lambda c, p=pol: p)''')
# gate report: verdict from dqn:main only; ablations printed with the same criterion
rep('''    g1, g5, g25 = (summary.get(f"gate@{c}", {}).get("pass", False) for c in CAPS)''',
    '''    for abl in ("dqn:bandit", "dqn:vanilla"):
        print(f"\n## ablation (does NOT change the verdict): U({abl}) - U(random:45), validation slice")
        for cap in caps:
            if not len(U(abl, cap)):
                continue
            d = U(abl, cap) - U("random:45", cap)
            lo, hi = paired_bootstrap_ci(d)
            ok = bool(d.mean() > 0 and lo > 0 and (d > 0).sum() >= need)
            summary[f"ablation[{abl}]@{cap}"] = {"mean_dU": float(d.mean()), "ci": [lo, hi],
                                                  "n_pos": int((d > 0).sum()), "criterion_met": ok}
            print(f"{cap:5.2f}{d.mean():10.4f}{'[%.4f, %.4f]' % (lo, hi):>22}{int((d > 0).sum()):>4}/{len(d)}"
                  f"  criterion met: {ok}")
    g1, g5, g25 = (summary.get(f"gate@{c}", {}).get("pass", False) for c in CAPS)''')
rep('''    names = list(dict.fromkeys(["dqn:main", "dqn:bandit", *REFS]''',
    '''    names = list(dict.fromkeys(["dqn:main", "dqn:bandit", "dqn:vanilla", *REFS]''')
p.write_text(s, encoding="utf-8")
print("patched")
