import pathlib
p = pathlib.Path("src/rlcache/config.py"); s = p.read_text(encoding="utf-8")
old = '''    n_bins: int = 4
    alpha: float = 0.1
    gamma: float = 0.95
    eps: float = 0.1
'''
new = '''    n_bins: int = 4
    alpha: float = 0.1
    gamma: float = 0.95
    eps: float = 0.1                         # floor
    eps_start: float = 1.0
    eps_decay_frac: float = 0.30
    total_decisions: int = 300_000
    calib_requests: int = 40_000             # random:45 calibration pass (normaliser + bin edges)
    min_visits_greedy: int = 1               # Amendment M8-a
'''
assert s.count(old) == 1
p.write_text(s.replace(old, new), encoding="utf-8")
