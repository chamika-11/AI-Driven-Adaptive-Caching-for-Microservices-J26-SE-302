import pathlib
p = pathlib.Path("src/rlcache/trace/synthetic.py")
s = p.read_text(encoding="utf-8")
def rep(old, new):
    global s
    assert s.count(old) == 1, old[:80]
    s = s.replace(old, new)
rep('''Shift = PopularityShift | FlashCrowd | WriteRateShift
''', '''@dataclass(frozen=True)
class DiurnalShift:
    """From ``at_frac`` on, read intensity becomes 1 + ``amp`` * sin(2 pi t / ``period_s``) (rate only, skew
    unchanged).  Read COUNT is preserved: post-shift arrival times are warped through the inverse CDF of that
    intensity on [at_frac*T, T] (Addendum M11-E, E3).  Intended for a base trace with ``diurnal_amp = 0``."""
    at_frac: float
    amp: float = 0.9
    period_s: float = 900.0


Shift = PopularityShift | FlashCrowd | WriteRateShift | DiurnalShift
''')
rep('''    cdf = truncated_zipf_cdf(n_keys, cfg.zipf_alpha)
    ranks =''', '''    for s in (s for s in shifts if isinstance(s, DiurnalShift)):
        t0 = s.at_frac * T
        late = r_ts >= t0
        if late.any():
            grid = np.linspace(t0, T, 4097)
            w = 2.0 * np.pi / s.period_s
            cdf_w = (grid - t0) + s.amp * (np.cos(w * t0) - np.cos(w * grid)) / w
            cdf_w /= cdf_w[-1]
            u = (r_ts[late] - t0) / (T - t0)
            r_ts[late] = np.interp(u, cdf_w, grid)
            r_ts.sort()
    cdf = truncated_zipf_cdf(n_keys, cfg.zipf_alpha)
    ranks =''')
p.write_text(s, encoding="utf-8")
print("ok")
