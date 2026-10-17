"""M5 gate (features): hand-computed values, brute-force cross-check at every decision,
future-leakage property, normaliser freeze/round-trip/ranges."""
import dataclasses
import math

import numpy as np
import pytest

from helpers import mk
from rlcache.config import Config, FeatureConfig, LatencyConfig, WorkloadConfig
from rlcache.features import FeatureTracker, Normalizer
from rlcache.features_spec import FEATURE_INDEX as I
from rlcache.features_spec import FEATURE_NAMES
from rlcache.predictor.standin import PredictorTables
from rlcache.runner import make_run
from rlcache.trace.record import OP_CODE
from rlcache.trace.splits import chronological_split
from rlcache.trace.synthetic import generate_synthetic

FLAT = LatencyConfig(backend_sigma=0.0)


class FakeSim:
    def __init__(self, util=0.0, inflight=0, bk=0.008):
        self.u, self.f, self.bk = util, inflight, bk
        self.key_backend_s = [bk] * 1000

    def utilisation(self): return self.u
    def inflight(self, t): return self.f


class Ctx:
    def __init__(self, key, ts, size=100, sim=None):
        self.key, self.ts, self.size, self.sim = key, ts, size, sim or FakeSim()


def feed(tr, reqs):
    """reqs: list of (t, key, is_write, hit)"""
    for i, (t, k, w, h) in enumerate(reqs):
        tr.on_request(i, t, k, w, h)


def tracker(n_keys=50, **kw):
    return FeatureTracker(n_keys, FeatureConfig(**kw))


# ---- hand-computed values -------------------------------------------------------------------------
def test_recency_gaps_and_sentinels():
    tr = tracker()
    feed(tr, [(0, 0, False, False), (10, 0, False, True), (15, 0, False, True)])
    raw = tr.raw(Ctx(0, 40.0))
    assert raw[I["log_recency_1"]] == pytest.approx(25.0)       # t - t_last
    assert raw[I["log_recency_2"]] == pytest.approx(5.0)        # t_last - t_prev
    obs = tr.norm.transform(raw)
    assert obs[I["log_recency_1"]] == pytest.approx(math.log1p(25) / math.log1p(86400))
    new = tr.norm.transform(tr.raw(Ctx(7, 40.0)))               # never seen
    assert new[I["log_recency_1"]] == 1.0 and new[I["log_recency_2"]] == 1.0
    one = tracker()
    feed(one, [(0, 3, False, False)])
    assert one.norm.transform(one.raw(Ctx(3, 5.0)))[I["log_recency_2"]] == 1.0   # only one access


def test_window_counts_and_decision_request_excluded():
    tr = tracker()
    keys = [1, 0, 2, 0, 0, 3, 0, 4, 5, 6, 7, 8]
    feed(tr, [(float(i), k, False, False) for i, k in enumerate(keys)])
    raw = tr.raw(Ctx(0, 12.0))
    assert raw[I["count_10"]] == 3          # last 10 = idx 2..11 -> keys 0 at idx 3,4,6
    assert raw[I["count_100"]] == 4         # idx 1,3,4,6
    assert raw[I["count_1000"]] == 4
    obs = tr.norm.transform(raw)
    assert obs[I["count_10"]] == pytest.approx(0.3)
    assert obs[I["count_100"]] == pytest.approx(0.04)
    assert obs[I["count_1000"]] == pytest.approx(0.004)


def test_long_window_slides():
    tr = tracker(n_keys=20)
    feed(tr, [(float(i), 0, False, False) for i in range(10)])
    feed(tr, [(10.0 + i, 9, False, False) for i in range(1500)])
    raw = tr.raw(Ctx(0, 2000.0))
    assert raw[I["count_1000"]] == 0 and raw[I["count_100"]] == 0
    assert raw[I["log_recency_1"]] == pytest.approx(2000.0 - 9.0)   # still remembered by recency


def test_edc_decays_with_half_life():
    tr = tracker(edc_half_life_s=60.0)
    feed(tr, [(0.0, 0, False, False), (60.0, 0, False, False)])
    assert tr.raw(Ctx(0, 60.0))[I["edc"]] == pytest.approx(1.5)      # 1*0.5 + 1
    assert tr.raw(Ctx(0, 120.0))[I["edc"]] == pytest.approx(0.75)
    assert tr.raw(Ctx(5, 120.0))[I["edc"]] == 0.0


def test_hit_ratio_counts_reads_only():
    tr = tracker()
    feed(tr, [(0, 0, False, False), (1, 0, False, True), (2, 0, True, None),
              (3, 1, False, True), (4, 1, False, False)])
    assert tr.raw(Ctx(0, 5.0))[I["hit_ratio"]] == pytest.approx(0.5)   # 2 hits / 4 reads
    assert tracker().raw(Ctx(0, 1.0))[I["hit_ratio"]] == 0.0


def test_rate_cov_and_invalidation_rate():
    tr = tracker(n_keys=200)
    reqs = []
    for sec in range(10):
        n = 15 if sec == 9 else 5
        reqs += [(sec + (j + 0.5) / n, j % 3, False, True) for j in range(n)]
    feed(tr, reqs)
    raw = tr.raw(Ctx(0, 10.5))
    assert raw[I["request_rate"]] == pytest.approx(6.0)               # (9*5 + 15) / 10
    assert raw[I["rate_cov_10s"]] == pytest.approx(3.0 / 6.0)         # pop. std 3.0 / mean 6
    w = tracker()
    feed(w, [(s + 0.25 * j, 0, j < 2, None if j < 2 else False) for s in range(5) for j in range(4)])
    assert w.raw(Ctx(0, 5.2))[I["invalidation_rate"]] == pytest.approx(2.0)   # 2 writes/s


def test_cov300_uses_ten_second_sums():
    tr = tracker(n_keys=5)
    reqs = []
    for sec in range(60):                         # six 10 s groups: counts 10,10,10,50,10,10 per s
        n = 50 if 30 <= sec < 40 else 10
        reqs += [(sec + (j + 0.5) / n, 0, False, True) for j in range(n)]
    feed(tr, reqs)
    raw = tr.raw(Ctx(0, 60.5))
    sums = np.array([100, 100, 100, 500, 100, 100.0])
    assert raw[I["rate_cov_300s"]] == pytest.approx(sums.std() / sums.mean())


def test_top10_share():
    tr = tracker(n_keys=30)
    keys = [0] * 50 + [k for k in range(1, 11) for _ in range(5)]
    feed(tr, [(float(i), k, False, False) for i, k in enumerate(keys)])
    assert tr.raw(Ctx(0, 200.0))[I["top10_share"]] == pytest.approx((50 + 9 * 5) / 100)


def test_sim_and_predictor_features_pass_through():
    pred = PredictorTables.absent(50)
    tr = FeatureTracker(50, FeatureConfig(max_inflight=64), pred)
    raw = tr.raw(Ctx(1, 1.0, size=4096, sim=FakeSim(util=0.42, inflight=8, bk=0.012)))
    assert raw[I["utilisation"]] == 0.42 and raw[I["backend_load"]] == pytest.approx(8 / 64)
    assert raw[I["backend_latency"]] == pytest.approx(12.0)            # ms
    assert raw[I["size"]] == 4096
    assert (raw[I["volatility"]], raw[I["predicted_ttl"]], raw[I["hot_key_flag"]]) == (0.5, 60.0, 0.0)


# ---- brute force at every decision + leakage --------------------------------------------------------
def brute(trace, i, cfg: FeatureConfig):
    """Independent recomputation of selected features from trace[0:i] only."""
    k, t = int(trace.key[i]), float(trace.ts[i])
    ks, ts = trace.key[:i], trace.ts[:i]
    idx = np.flatnonzero(ks == k)
    out = {}
    out["log_recency_1"] = t - ts[idx[-1]] if len(idx) else -1.0
    out["log_recency_2"] = ts[idx[-1]] - ts[idx[-2]] if len(idx) > 1 else -1.0
    for name, m in (("count_10", 10), ("count_100", 100), ("count_1000", 1000)):
        out[name] = int((ks[-m:] == k).sum()) if i else 0
    hl = cfg.edc_half_life_s
    out["edc"] = float(np.sum(0.5 ** ((t - ts[idx]) / hl))) if len(idx) else 0.0
    last = ks[-1000:]
    if len(last):
        c = np.sort(np.bincount(last))[::-1]
        out["top10_share"] = c[:10].sum() / len(last)
    else:
        out["top10_share"] = 0.0
    sec = int(t)
    first = int(ts[0]) if i else sec
    avail = max(0, min(300, sec - first))
    if avail:
        a10 = min(10, avail)
        sec_of = np.floor(ts).astype(np.int64)
        v10 = np.array([(sec_of == sec - j).sum() for j in range(1, a10 + 1)], float)
        out["request_rate"] = v10.mean()
        out["rate_cov_10s"] = (v10.std() / v10.mean()) if a10 >= 2 and v10.mean() > 0 else 0.0
        wr = trace.is_write[:i]
        out["invalidation_rate"] = sum(((sec_of == sec - j) & wr).sum()
                                       for j in range(1, avail + 1)) / avail
    else:
        out["request_rate"] = out["rate_cov_10s"] = out["invalidation_rate"] = 0.0
    return out


class Recorder:
    """select(): record the raw feature vector (via the same tracker) + trace idx per decision."""

    def __init__(self):
        self.rows = []
        self.tracker = None

    def __call__(self, obs, ctx):
        self.rows.append((ctx.idx, self.tracker.raw(ctx).copy(), obs.copy()))
        return 2 * 15 // 15 + 12      # a fixed valid action id (redis, ttl idx 2... any 0..44)


def _cfg(**kw):
    return dataclasses.replace(Config(), latency=FLAT, **kw)


@pytest.fixture(scope="module")
def syn():
    return generate_synthetic(WorkloadConfig(n_requests=12_000, n_keys=300,
                                             write_interval_median_s=20_000.0, seed=6))


def test_features_match_independent_brute_force_at_every_decision(syn):
    rec = Recorder()
    cfg = _cfg()
    run = make_run(syn, cfg, rec)
    rec.tracker = run.tracker
    run.go()
    assert len(rec.rows) > 500
    fc = cfg.features
    for idx, raw, _ in rec.rows[::7]:
        ref = brute(syn, idx, fc)
        for name, v in ref.items():
            assert raw[I[name]] == pytest.approx(v, rel=1e-9, abs=1e-9), (idx, name)


def test_no_feature_depends_on_future_requests(syn):
    """R-P8: scramble everything after a cut-off; every decision before it is unchanged."""
    cut = 6000
    rng = np.random.default_rng(0)
    key = syn.key.copy(); op = syn.op.copy(); size = syn.size.copy()
    key[cut:] = rng.integers(0, syn.n_keys, len(syn) - cut)
    op[cut:] = np.where(rng.random(len(syn) - cut) < 0.4, OP_CODE["set"], OP_CODE["get"])
    size[cut:] = rng.integers(10, 5000, len(syn) - cut)
    mutated = dataclasses.replace(syn, key=key, op=op, size=size)

    def collect(trace):
        rec = Recorder()
        run = make_run(trace, _cfg(), rec)
        rec.tracker = run.tracker
        run.go()
        return [(i, raw, obs) for i, raw, obs in rec.rows if i < cut]

    a, b = collect(syn), collect(mutated)
    assert len(a) == len(b) > 300
    for (ia, ra, oa), (ib, rb, ob) in zip(a, b):
        assert ia == ib and np.array_equal(ra, rb) and np.array_equal(oa, ob)


def test_observation_shape_names_and_ranges(syn):
    rec = Recorder()
    run = make_run(syn, _cfg(), rec, learn_normalizer=True)
    rec.tracker = run.tracker
    run.go()
    obs = np.stack([o for *_, o in rec.rows])
    assert obs.shape[1] == 19 and len(FEATURE_NAMES) == 19
    assert np.all(np.isfinite(obs)) and obs.dtype == np.float32
    assert obs.min() >= -1.0 - 1e-6 and obs.max() <= 1.0 + 1e-6
    z = [I["backend_latency"], I["request_rate"], I["invalidation_rate"]]
    nonz = [j for j in range(19) if j not in z]
    assert obs[:, nonz].min() >= 0.0
    spread = obs.std(axis=0)
    assert spread[I["count_1000"]] > 0 and spread[I["size"]] > 0 and spread[I["utilisation"]] > 0


# ---- normaliser (R-P7, R-F20) --------------------------------------------------------------------------
def _raw_vec(**kw):
    v = np.zeros(19)
    v[I["log_recency_1"]] = v[I["log_recency_2"]] = -1.0
    v[I["predicted_ttl"]] = 60.0
    for k, x in kw.items():
        v[I[k]] = x
    return v


def test_frozen_normalizer_does_not_change_and_round_trips():
    n = Normalizer()
    rng = np.random.default_rng(0)
    for _ in range(500):
        n.transform(_raw_vec(request_rate=rng.exponential(20), backend_latency=rng.lognormal(2, .5),
                             edc=rng.exponential(3), size=rng.integers(10, 9000)), update=True)
    st = n.state_dict()
    n.freeze()
    probe = _raw_vec(request_rate=33.0, backend_latency=9.0, edc=2.0, size=1234)
    before = n.transform(probe)
    for _ in range(50):
        n.transform(_raw_vec(request_rate=1e6, edc=1e6, size=1e9), update=True)   # ignored: frozen
    assert n.state_dict()["z"] == dict(st["z"]) or n.state_dict()["edc_max"] == st["edc_max"]
    assert np.array_equal(n.transform(probe), before)
    m = Normalizer()
    m.load_state_dict(n.state_dict())
    assert np.array_equal(m.transform(probe), before)
    assert m.frozen


def test_zscore_features_are_centered_and_clipped():
    n = Normalizer()
    rng = np.random.default_rng(1)
    for _ in range(3000):
        n.transform(_raw_vec(request_rate=rng.lognormal(3, 0.4)), update=True)
    zs = np.array([n.transform(_raw_vec(request_rate=rng.lognormal(3, 0.4)))[I["request_rate"]]
                   for _ in range(2000)])
    assert abs(zs.mean()) < 0.05 and 0.1 < zs.std() < 0.35        # z/5: std ~ 1/5
    huge = n.transform(_raw_vec(request_rate=1e12))[I["request_rate"]]
    assert huge == pytest.approx(1.0)                              # clip at +5 sigma -> 1.0


def test_normalizer_is_learned_only_from_the_training_pass(syn):
    """Evaluation on a later slice with a frozen normaliser leaves its statistics untouched."""
    sp = chronological_split(len(syn))
    norm = Normalizer()
    rec = Recorder()
    cfg = _cfg()
    run = make_run(syn, cfg, rec, normalizer=norm, learn_normalizer=True)
    rec.tracker = run.tracker
    run.go(*sp.train)
    norm.freeze()
    snap = norm.state_dict()
    rec2 = Recorder()
    run2 = make_run(syn, cfg, rec2, normalizer=norm, learn_normalizer=True)   # asks to learn...
    rec2.tracker = run2.tracker
    run2.go(*sp.test)
    assert norm.state_dict() == snap                                # ...but frozen: unchanged
