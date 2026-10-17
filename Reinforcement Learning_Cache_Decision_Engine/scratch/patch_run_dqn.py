import pathlib

p = pathlib.Path("scripts/run_dqn.py")
s = p.read_text(encoding="utf-8")


def rep(old, new):
    global s
    assert s.count(old) == 1, old[:70]
    s = s.replace(old, new)


rep('ARCH = {"dqn": (True, True), "dqn_bandit": (True, True), "dqn_vanilla": (False, False)}',
    'ARCH = {"dqn": (True, True), "dqn_bandit": (True, True), "dqn_vanilla": (False, False),\n'
    '        "dqn_perkey": (True, True)}\n'
    '# Amendment M9-e: repair arm, NOT in the default variant list (so eval/dev defaults are unchanged)\n'
    'EXTRA_VARIANTS = {"dqn_perkey": 0.95}\n'
    'SUCCESSOR = {"dqn_perkey": "same_key"}         # every other variant keeps the D-9 successor "any"')
rep("    gamma = VARIANTS[variant]", "    gamma = {**VARIANTS, **EXTRA_VARIANTS}[variant]")
rep("""    res = T.train_dqn(ctx, make_learner(backend, ctx.seed, variant), cfg, gamma=gamma,
                      calib_requests=40_000 if not decisions else 4_000)""",
    """    succ = SUCCESSOR.get(variant, "any")
    res = T.train_dqn(ctx, make_learner(backend, ctx.seed, variant), cfg, gamma=gamma,
                      calib_requests=40_000 if not decisions else 4_000, successor=succ)""")
rep("""f"last_loss={last[1]:.5f} last_Qmean={last[2]:.3f} last_Qmax={last[3]:.3f} \"""",
    """f"successor={succ} dropped_tail={res.diag.get('dropped_tail')} emitted={res.diag.get('emitted')} "
                      f"last_loss={last[1]:.5f} last_Qmean={last[2]:.3f} last_Qmax={last[3]:.3f} \"""")
p.write_text(s, encoding="utf-8")
print("ok")
