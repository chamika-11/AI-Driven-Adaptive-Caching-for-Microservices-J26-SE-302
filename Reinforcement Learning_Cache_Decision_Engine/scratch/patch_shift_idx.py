import pathlib

p = pathlib.Path("src/rlcache/shift.py")
s = p.read_text(encoding="utf-8")


def rep(old, new):
    global s
    assert s.count(old) == 1, old[:70]
    s = s.replace(old, new)


rep('"write10": WriteRateShift(at_frac, factor=10.0),', '"write10": WriteRateShift(WRITE10_AT_FRAC, factor=10.0),')
rep('AT_FRAC = 0.88\n', 'AT_FRAC = 0.88\nWRITE10_AT_FRAC = 0.914          # puts the x10 write shift at request index ~0.88 N (Amendment M11-E-b)\n')
rep('''def shift_index(trace: Trace, at_frac: float = AT_FRAC, duration_s: float | None = None) -> int:
    T = duration_s if duration_s is not None else float(WorkloadConfig().duration_s)
    return int(np.searchsorted(trace.ts, at_frac * T, side="left"))''',
    '''def shift_index(trace: Trace, at_frac: float | None = None, duration_s: float | None = None) -> int:
    """First request at or after the shift (time fraction read from the trace's recorded shift)."""
    if at_frac is None:
        at_frac = float(trace.meta["shifts"][0].at_frac)
    T = duration_s if duration_s is not None else float(WorkloadConfig().duration_s)
    return int(np.searchsorted(trace.ts, at_frac * T, side="left"))''')
p.write_text(s, encoding="utf-8")

p = pathlib.Path("tests/test_shift.py")
s = p.read_text(encoding="utf-8")
rep("assert 0.85 * len(tr) < t_star < 0.93 * len(tr)", "assert 0.87 * len(tr) < t_star < 0.89 * len(tr)")
p.write_text(s, encoding="utf-8")
print("ok")
