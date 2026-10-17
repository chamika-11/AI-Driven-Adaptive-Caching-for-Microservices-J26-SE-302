"""M3 gate: predictor fits only [0, fit_end); accuracy=1 == fitted truth; accuracy=0 is a
permutation (same marginal); marginal preservation; leakage; defaults when absent."""
import dataclasses

import numpy as np
import pytest

from rlcache.config import WorkloadConfig
from rlcache.predictor import standin as PR
from rlcache.trace.record import OP_CODE, Trace
from rlcache.trace.splits import chronological_split
from rlcache.trace.synthetic import generate_synthetic

CFG = WorkloadConfig(n_requests=60_000, n_keys=600, duration_s=8 * 3600.0,
                     write_interval_median_s=4000.0, seed=11)


@pytest.fixture(scope="module")
def tr():
    return generate_synthetic(CFG)


@pytest.fixture(scope="module")
def tables(tr):
    return PR.PredictorTables.fit(tr, chronological_split(len(tr)).fit_end)


def _mk(ts, key, op, n_keys=5):
    n = len(ts)
    return Trace(np.asarray(ts, float), np.asarray(key, np.int64), np.full(n, 100, np.int32),
                 np.zeros(n, np.int32), np.asarray(op, np.int8), np.zeros(n, np.int32), n_keys)


SET, GET = OP_CODE["set"], OP_CODE["get"]


# ---- statistics, hand-computed -----------------------------------------------------------------
def test_predicted_ttl_hand_computed():
    # key0 writes at 0,10,30,60 -> gaps 10,20,30 ; 20th pct (linear) = 10 + 0.4*(20-10)= 14
    # key1 writes at 5 only -> never gapped -> 3600 ;  key2 only reads -> 3600
    # key3 writes at 0, 0.2 -> gap 0.2 -> clipped up to floor 1.0
    t = _mk([0, 5, 10, 30, 60, 0.0, 0.2], [0, 1, 0, 0, 0, 3, 3],
            [SET, SET, SET, SET, SET, SET, SET])
    t = _mk(*zip(*sorted(zip(t.ts, t.key, t.op))))
    ttl = PR.compute_predicted_ttl(t)
    assert ttl[0] == pytest.approx(14.0)
    assert ttl[1] == 3600.0 and ttl[2] == 3600.0 and ttl[4] == 3600.0
    assert ttl[3] == 1.0


def test_group_quantile_matches_numpy():
    rng = np.random.default_rng(0)
    keys = rng.integers(0, 7, 400)
    gaps = rng.exponential(30.0, 400)
    got = PR._group_quantile(keys, gaps, 9, 0.2)
    for k in range(7):
        assert got[k] == pytest.approx(np.quantile(gaps[keys == k], 0.2))
    assert np.isnan(got[7]) and np.isnan(got[8])


def test_volatility_hand_computed_and_bounded():
    # key0: 4 evenly spaced writes (CV 0) + 4 reads over 100 s -> f=4/100, r=4/8
    ts = [0, 10, 20, 30, 40, 50, 60, 100]
    key = [0, 0, 0, 0, 0, 0, 0, 0]
    op = [SET, SET, SET, SET, GET, GET, GET, GET]
    t = _mk(ts, key, op)
    v = PR.compute_volatility(t)
    f_norm = 1 - np.exp(-(4 / 100.0) * 300.0)
    expected = 0.5 * f_norm + 0.3 * (4 / 8) + 0.2 * 0.0
    assert v[0] == pytest.approx(expected, abs=1e-6)
    assert np.all((v >= 0) & (v <= 1))
    assert np.all(v[1:] == 0.0)                           # untouched keys


def test_volatility_orders_keys_by_write_rate():
    fast = _mk(list(range(0, 200, 2)), [0] * 100, [SET] * 100)
    slow = _mk([0, 190], [0, 0], [SET, SET])
    assert PR.compute_volatility(fast)[0] > PR.compute_volatility(slow)[0]


def test_hot_flag_top_one_percent_and_tie_handling():
    n_keys = 300
    keys = np.concatenate([np.full(500, 0), np.full(300, 1), np.arange(2, n_keys).repeat(2)])
    t = _mk(np.arange(len(keys), dtype=float), keys, [GET] * len(keys), n_keys=n_keys)
    hot = PR.compute_hot_flag(t)
    assert hot[0] == 1 and hot[1] == 1
    assert hot[2:].sum() == 0                              # 298 tied keys must NOT be flagged
    assert hot.sum() <= int(np.ceil(0.01 * n_keys))


def test_hot_flag_never_flags_more_than_k_and_all_tied_means_none():
    n_keys = 500
    tied = _mk(np.arange(n_keys * 3, dtype=float), np.arange(n_keys).repeat(3),
               [GET] * (n_keys * 3), n_keys=n_keys)
    assert PR.compute_hot_flag(tied).sum() == 0            # no key distinguishable as hot
    rng = np.random.default_rng(0)
    zipf = rng.zipf(1.5, 20_000) % n_keys
    z = _mk(np.arange(len(zipf), dtype=float), zipf, [GET] * len(zipf), n_keys=n_keys)
    seen = (np.bincount(zipf, minlength=n_keys) > 0).sum()
    assert 0 < PR.compute_hot_flag(z).sum() <= int(np.ceil(0.01 * seen))


# ---- frozen split / leakage (R-P3, R-P8) ------------------------------------------------------------
def test_fit_ignores_everything_after_fit_end(tr, tables):
    sp = chronological_split(len(tr))
    mutated = dataclasses.replace(tr)
    key = tr.key.copy(); op = tr.op.copy()
    rng = np.random.default_rng(1)
    key[sp.fit_end:] = rng.integers(0, tr.n_keys, len(tr) - sp.fit_end)   # scramble the future
    op[sp.fit_end:] = np.where(rng.random(len(tr) - sp.fit_end) < 0.9, SET, GET)
    mutated = dataclasses.replace(tr, key=key, op=op)
    t2 = PR.PredictorTables.fit(mutated, sp.fit_end)
    for f in ("volatility", "predicted_ttl", "hot_key"):
        assert np.array_equal(getattr(tables, f), getattr(t2, f))


def test_fit_on_prefix_equals_fit_on_longer_trace(tr, tables):
    sp = chronological_split(len(tr))
    short = tr.slice(0, int(len(tr) * 0.5))
    t2 = PR.PredictorTables.fit(short, sp.fit_end)
    assert np.array_equal(tables.predicted_ttl, t2.predicted_ttl)
    assert np.array_equal(tables.volatility, t2.volatility)


def test_tables_are_frozen(tables):
    with pytest.raises(ValueError):
        tables.volatility[0] = 0.9
    assert tables.meta["uses_future"] is False


def test_oracle_bound_differs_and_is_labelled(tr, tables):
    orc = PR.PredictorTables.oracle_bound(tr)
    assert orc.meta["uses_future"] is True and orc.meta["source"] == "oracle_bound"
    assert not np.array_equal(orc.predicted_ttl, tables.predicted_ttl)


def test_fitted_volatility_varies_across_keys(tables, tr):
    sp = chronological_split(len(tr))
    seen = np.bincount(tr.key[:sp.fit_end], minlength=tr.n_keys) > 0
    v = tables.volatility[seen]
    assert v.std() > 0.02 and np.percentile(v, 95) > 3 * np.percentile(v, 25)   # R-D10
    assert tables.predicted_ttl[seen].min() < 600 and tables.predicted_ttl[seen].max() == 3600


def test_fitted_tables_carry_signal_about_the_future(tr, tables):
    """The fitted (causal) volatility must correlate with the hidden true write rate."""
    from scipy.stats import spearmanr
    seen = np.bincount(tr.key[:int(0.3 * len(tr))], minlength=tr.n_keys) > 0
    assert spearmanr(tables.volatility[seen], tr.meta["true_write_rate"][seen]).statistic > 0.4


# ---- accuracy knob (R-P4) -----------------------------------------------------------------------------
def test_accuracy_one_equals_truth(tables):
    t1 = tables.with_accuracy(1.0, np.random.default_rng(0))
    for f in ("volatility", "predicted_ttl", "hot_key"):
        assert np.array_equal(getattr(tables, f), getattr(t1, f))
    t1i = tables.with_accuracy(1.0, np.random.default_rng(0), mode="interpolate")
    assert np.allclose(tables.volatility, t1i.volatility)


def test_accuracy_zero_is_permutation_same_marginal(tables):
    t0 = tables.with_accuracy(0.0, np.random.default_rng(0))
    for f in ("volatility", "predicted_ttl", "hot_key"):
        a, b = getattr(tables, f), getattr(t0, f)
        assert np.array_equal(np.sort(a), np.sort(b))     # identical multiset of values
    assert not np.array_equal(tables.predicted_ttl, t0.predicted_ttl)
    # no information: correlation with truth ~ 0
    assert abs(np.corrcoef(tables.volatility, t0.volatility)[0, 1]) < 0.15


def test_mixture_preserves_marginal_at_intermediate_accuracy(tables):
    base = tables.volatility
    for a in (0.25, 0.5, 0.75):
        v = tables.with_accuracy(a, np.random.default_rng(3)).volatility
        assert v.mean() == pytest.approx(base.mean(), rel=0.15)
        assert v.std() == pytest.approx(base.std(), rel=0.15)        # marginal preserved


def test_interpolate_mode_shrinks_variance_contradicting_md_claim(tables):
    """C-33: the MD claims the marginal is identical at every accuracy; it is not."""
    base_sd = tables.volatility.std()
    v = tables.with_accuracy(0.5, np.random.default_rng(3), mode="interpolate").volatility
    assert v.std() < 0.85 * base_sd                                  # ~ sqrt(0.5) = 0.71


def test_accuracy_is_monotone_in_agreement_with_truth(tables):
    corr = []
    for a in (0.0, 0.25, 0.5, 0.75, 1.0):
        v = tables.with_accuracy(a, np.random.default_rng(7)).volatility
        corr.append(np.corrcoef(tables.volatility, v)[0, 1])
    assert corr == sorted(corr) and corr[-1] == pytest.approx(1.0) and corr[0] < 0.2


def test_fields_share_one_permutation(tables):
    """volatility/ttl/hot of one key must stay mutually consistent after degradation."""
    t = tables.with_accuracy(0.0, np.random.default_rng(5))
    pairs_true = set(zip(tables.volatility.tolist(), tables.predicted_ttl.tolist()))
    pairs_deg = set(zip(t.volatility.tolist(), t.predicted_ttl.tolist()))
    assert pairs_deg <= pairs_true                                   # rows moved, not mixed


def test_single_array_helper_matches_contract():
    rng = np.random.default_rng(0)
    x = np.linspace(1, 3600, 200).astype(np.float32)
    assert np.array_equal(PR.synthetic_predictor(x, 1.0, rng), x)
    z = PR.synthetic_predictor(x, 0.0, np.random.default_rng(0))
    assert np.array_equal(np.sort(z), np.sort(x))
    with pytest.raises(ValueError):
        PR.synthetic_predictor(x, 0.5, rng, mode="bogus")


# ---- predictor absent (R-P6) -------------------------------------------------------------------------
def test_absent_predictor_is_constant_and_documented():
    a = PR.PredictorTables.absent(50)
    assert np.all(a.volatility == PR.ABSENT_VOLATILITY)
    assert np.all(a.predicted_ttl == PR.ABSENT_TTL_S)
    assert np.all(a.hot_key == 0.0)
    assert a.meta["source"] == "absent"
    assert a.lookup(3) == (0.5, 60.0, 0.0)


def test_gap_stats_for_statistics_ttl_baselines(tr):
    sp = chronological_split(len(tr))
    gs = PR.fit_gap_stats(tr.slice(0, sp.fit_end))
    has = gs.n_gaps > 0
    assert np.all(gs.p10[has] <= gs.median[has] + 1e-9)
    assert np.all(np.isnan(gs.mean[~has]))
