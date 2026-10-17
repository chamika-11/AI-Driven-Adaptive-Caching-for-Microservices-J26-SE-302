"""M2 gate (generator, splitter, oracle)."""
import dataclasses

import numpy as np
import pytest

from rlcache.config import SplitConfig, WorkloadConfig
from rlcache.trace import synthetic as S
from rlcache.trace.oracle import annotate_oracle
from rlcache.trace.record import NO_FUTURE_IDX, Trace
from rlcache.trace.splits import chronological_split, split_traces

SMALL = WorkloadConfig(n_requests=60_000, n_keys=800, duration_s=8 * 3600.0, seed=3)


@pytest.fixture(scope="module")
def tr():
    return S.generate_synthetic(SMALL)


# ---- generator --------------------------------------------------------------------------------
def test_basic_shape_and_span(tr):
    assert len(tr) == SMALL.n_requests
    assert tr.duration_s >= 6 * 3600                     # D-15: TTL 3600 can expire
    assert np.all(np.diff(tr.ts) >= 0)
    assert tr.key.min() >= 0 and tr.key.max() < SMALL.n_keys
    assert 0.05 < tr.write_fraction() < 0.6
    tr.validate()


def test_per_key_write_rate_spread(tr):
    """Gate: volatility must vary across keys, otherwise the feature is dead weight (R-D10)."""
    w = np.bincount(tr.key[tr.is_write], minlength=tr.n_keys).astype(float)
    r = np.bincount(tr.key[tr.is_read], minlength=tr.n_keys)
    ok = r >= 1
    p10, p90 = np.percentile(w[ok], [10, 90])
    assert p90 > 5 * max(p10, 1.0)
    lam = tr.meta["true_write_rate"]
    assert np.percentile(lam, 95) / np.percentile(lam, 5) > 50   # heavy lognormal spread
    # empirical per-key write counts track the hidden rate (rank correlation is high)
    from scipy.stats import spearmanr
    assert spearmanr(w, lam).statistic > 0.8


def test_time_to_next_write_spans_ttl_decades():
    """Every TTL decade must be the 'right' answer for a non-trivial share of reads (D-15)."""
    t = S.generate_synthetic(WorkloadConfig(n_requests=120_000, n_keys=1500, seed=1))
    o = annotate_oracle(t)
    rd = t.is_read
    d = o.next_write_ts[rd] - t.ts[rd]
    for lo, hi in [(0, 30), (30, 600), (600, 3600)]:
        assert ((d >= lo) & (d < hi)).mean() > 0.02


def test_deterministic_under_seed():
    a = S.generate_synthetic(SMALL)
    b = S.generate_synthetic(SMALL)
    c = S.generate_synthetic(dataclasses.replace(SMALL, seed=4))
    assert np.array_equal(a.key, b.key) and np.array_equal(a.ts, b.ts)
    assert not np.array_equal(a.key, c.key)


def test_zipf_alpha_controls_skew():
    def top_share(alpha):
        t = S.generate_synthetic(dataclasses.replace(SMALL, zipf_alpha=alpha, locality_prob=0.0))
        c = np.sort(np.bincount(t.key[t.is_read], minlength=t.n_keys))[::-1]
        return c[:8].sum() / c.sum()
    shares = [top_share(a) for a in (0.6, 0.8, 0.99, 1.2)]
    assert shares == sorted(shares) and shares[-1] > 2 * shares[0]


def test_zipf_is_truncated_not_folded():
    cdf = S.truncated_zipf_cdf(100, 1.0)
    assert cdf[-1] == pytest.approx(1.0) and len(cdf) == 100
    p = np.diff(np.concatenate([[0], cdf]))
    assert np.all(np.diff(p) <= 1e-12)                  # strictly non-increasing by rank


def test_temporal_locality_increases_window_reuse():
    """Flat popularity over a huge key space gives ~no reuse, so any reuse inside the 1000-request
    window is attributable to the locality redraw (expected lift ~ locality_prob)."""
    def reuse(p):
        cfg = dataclasses.replace(SMALL, n_keys=20_000, n_requests=40_000, zipf_alpha=0.1,
                                  locality_prob=p, write_interval_median_s=1e9, seed=5)
        t = S.generate_synthetic(cfg)
        k = t.key[t.is_read].tolist()
        last, hits = {}, 0
        for i, x in enumerate(k):
            if i - last.get(x, -10**9) <= cfg.locality_window:
                hits += 1
            last[x] = i
        return hits / len(k)
    base, loc = reuse(0.0), reuse(0.3)
    assert base < 0.15
    assert loc > base + 0.2


def test_popularity_shift_changes_hot_set():
    cfg = dataclasses.replace(SMALL, locality_prob=0.0)
    t = S.generate_synthetic(cfg, shifts=[S.PopularityShift(0.5, retention=0.0)])
    half = cfg.duration_s / 2
    r = t.is_read
    a = np.bincount(t.key[r & (t.ts < half)], minlength=t.n_keys)
    b = np.bincount(t.key[r & (t.ts >= half)], minlength=t.n_keys)
    top_a, top_b = set(np.argsort(a)[-20:]), set(np.argsort(b)[-20:])
    assert len(top_a & top_b) < 8
    same = S.generate_synthetic(cfg, shifts=[S.PopularityShift(0.5, retention=1.0)])
    a2 = np.bincount(same.key[same.is_read & (same.ts < half)], minlength=t.n_keys)
    b2 = np.bincount(same.key[same.is_read & (same.ts >= half)], minlength=t.n_keys)
    assert len(set(np.argsort(a2)[-20:]) & set(np.argsort(b2)[-20:])) > 12


def test_flash_crowd_concentrates_traffic():
    cfg = dataclasses.replace(SMALL, locality_prob=0.0)
    t = S.generate_synthetic(cfg, shifts=[S.FlashCrowd(0.4, 0.2, n_hot=5, boost=0.5)])
    T = cfg.duration_s
    w = t.is_read & (t.ts >= 0.4 * T) & (t.ts < 0.6 * T)
    c = np.sort(np.bincount(t.key[w], minlength=t.n_keys))[::-1]
    assert c[:5].sum() / c.sum() > 0.4
    base = S.generate_synthetic(cfg)
    wb = base.is_read & (base.ts >= 0.4 * T) & (base.ts < 0.6 * T)
    cb = np.sort(np.bincount(base.key[wb], minlength=base.n_keys))[::-1]
    assert c[:5].sum() / c.sum() > cb[:5].sum() / cb.sum() + 0.2   # relative to Zipf baseline


def test_write_rate_shift_multiplies_writes():
    cfg = dataclasses.replace(SMALL, n_requests=200_000, write_interval_median_s=40_000.0)
    t = S.generate_synthetic(cfg, shifts=[S.WriteRateShift(0.5, factor=10.0)])
    half = cfg.duration_s / 2
    w_before = ((t.ts < half) & t.is_write).sum()
    w_after = ((t.ts >= half) & t.is_write).sum()
    assert 7 < w_after / max(w_before, 1) < 13


def test_write_volume_guard():
    with pytest.raises(ValueError):
        S.generate_synthetic(dataclasses.replace(SMALL, write_interval_median_s=60.0))


# ---- splitter ---------------------------------------------------------------------------------
def test_split_is_chronological_contiguous_and_exhaustive(tr):
    sp, parts = split_traces(tr)
    assert sp.fit == (0, int(0.3 * len(tr)))
    assert sp.test[1] == len(tr)
    assert sp.fit[1] == sp.train[0] and sp.train[1] == sp.val[0] and sp.val[1] == sp.test[0]
    assert sum(len(p) for p in parts.values()) == len(tr)
    ends = [parts[k].ts[-1] for k in ("fit", "train", "val")]
    starts = [parts[k].ts[0] for k in ("train", "val", "test")]
    assert all(e <= s for e, s in zip(ends, starts))     # no temporal overlap -> no look-ahead


def test_split_fractions_are_d8(tr):
    sp = chronological_split(1000)
    assert (sp.fit_end, sp.train_end, sp.val_end) == (300, 700, 800)
    with pytest.raises(ValueError):
        chronological_split(5)
    sp2 = chronological_split(1000, SplitConfig(0.2, 0.5, 0.6))
    assert (sp2.fit_end, sp2.train_end, sp2.val_end) == (200, 500, 600)


# ---- oracle -----------------------------------------------------------------------------------
def _brute(tr: Trace):
    n = len(tr)
    na = np.full(n, NO_FUTURE_IDX, dtype=np.int64)
    nw = np.full(n, NO_FUTURE_IDX, dtype=np.int64)
    for i in range(n):
        for j in range(i + 1, n):
            if tr.key[j] == tr.key[i]:
                if na[i] == NO_FUTURE_IDX:
                    na[i] = j
                if tr.is_write[j] and nw[i] == NO_FUTURE_IDX:
                    nw[i] = j
                    break
    return na, nw


def test_oracle_matches_brute_force_on_small_trace():
    t = S.generate_synthetic(WorkloadConfig(n_requests=600, n_keys=15, duration_s=7200.0,
                                            write_interval_median_s=6000.0, seed=9))
    o = annotate_oracle(t)
    na, nw = _brute(t)
    assert np.array_equal(o.next_access_idx, na)
    assert np.array_equal(o.next_write_idx, nw)
    # timestamps are consistent with indices and are in the future
    has = o.next_access_idx != NO_FUTURE_IDX
    assert np.all(o.next_access_ts[has] == t.ts[o.next_access_idx[has]])
    assert np.all(o.next_access_ts[has] >= t.ts[has])
    assert np.all(np.isinf(o.next_write_ts[o.next_write_idx == NO_FUTURE_IDX]))


def test_next_write_is_never_earlier_than_next_access_when_write_follows():
    t = S.generate_synthetic(WorkloadConfig(n_requests=3000, n_keys=40, duration_s=7200.0,
                                            write_interval_median_s=1800.0, seed=2))
    o = annotate_oracle(t)
    assert np.all(o.next_write_idx >= o.next_access_idx)   # the next write IS some later access
