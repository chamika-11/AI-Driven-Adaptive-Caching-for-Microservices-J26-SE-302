import pathlib
p = pathlib.Path("src/rlcache/analysis/signal.py"); s = p.read_text(encoding="utf-8")
def rep(a, b):
    global s
    assert s.count(a) == 1, a[:60]
    s = s.replace(a, b)
rep('''def accuracy_point(seed: int, capacity: float, accuracy: float, mode: str = "mixture",
                   arm: str = "harsh", ctx: EvalContext | None = None) -> dict:
    """One (seed, capacity, accuracy) evaluation of the test policy on the test slice."""
    ctx = ctx or EvalContext.build(seed, capacity, arm)''',
'''def accuracy_point(seed: int, capacity: float, accuracy: float, mode: str = "mixture",
                   arm: str = "harsh", ctx: EvalContext | None = None, workload=None) -> dict:
    """One (seed, capacity, accuracy) evaluation of the test policy on the test slice."""
    ctx = ctx or EvalContext.build(seed, capacity, arm, workload=workload)''')
rep('''def collect_obs_targets(seed: int, capacity: float, accuracy: float, arm: str = "harsh"):''',
    '''def collect_obs_targets(seed: int, capacity: float, accuracy: float, arm: str = "harsh",
                        workload=None):''')
rep('''    ctx = EvalContext.build(seed, capacity, arm)
    tables = ctx.predictor.with_accuracy''', '''    ctx = EvalContext.build(seed, capacity, arm, workload=workload)
    tables = ctx.predictor.with_accuracy''')
rep('''def feature_regression(seed: int, capacity: float, arm: str = "harsh") -> dict:
    X1tr, y1tr, X1te, y1te = collect_obs_targets(seed, capacity, 1.0, arm)
    X0tr, y0tr, X0te, y0te = collect_obs_targets(seed, capacity, 0.0, arm)''',
'''def feature_regression(seed: int, capacity: float, arm: str = "harsh", workload=None,
                       epochs: int = 8) -> dict:
    X1tr, y1tr, X1te, y1te = collect_obs_targets(seed, capacity, 1.0, arm, workload)
    X0tr, y0tr, X0te, y0te = collect_obs_targets(seed, capacity, 0.0, arm, workload)''')
rep("    r2_1 = fit_and_score_mlp(X1tr, y1tr, X1te, y1te, seed)\n    r2_0 = fit_and_score_mlp(X0tr, y0tr, X0te, y0te, seed)\n    r2_np = fit_and_score_mlp(nop_tr, y1tr, nop_te, y1te, seed)",
    "    r2_1 = fit_and_score_mlp(X1tr, y1tr, X1te, y1te, seed, epochs)\n    r2_0 = fit_and_score_mlp(X0tr, y0tr, X0te, y0te, seed, epochs)\n    r2_np = fit_and_score_mlp(nop_tr, y1tr, nop_te, y1te, seed, epochs)")
p.write_text(s, encoding="utf-8")
