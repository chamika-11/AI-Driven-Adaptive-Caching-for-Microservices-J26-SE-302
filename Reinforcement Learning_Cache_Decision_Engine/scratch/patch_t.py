import pathlib
p = pathlib.Path("tests/test_dqn_numpy.py"); s = p.read_text(encoding="utf-8")
a = "    a = T.train_dqn(ctx, _learner(), SMALL, calib_requests=2_000)\n    b = T.train_dqn(ctx, _learner(), SMALL, calib_requests=2_000)\n    assert a.decisions == 3_000 and a.norm.frozen"
assert s.count(a) == 1
b = "    a = T.train_dqn(ctx, _learner(), SMALL, calib_requests=2_000, log_every=400)\n    b = T.train_dqn(ctx, _learner(), SMALL, calib_requests=2_000, log_every=400)\n    assert a.decisions == 3_000 and a.norm.frozen"
p.write_text(s.replace(a, b), encoding="utf-8")
