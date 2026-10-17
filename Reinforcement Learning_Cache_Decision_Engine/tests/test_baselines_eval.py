"""M6 gate: Pareto utilities, baseline policies, Belady bounds (vs brute force), evaluation
runner invariants, reporting."""
import dataclasses
import itertools
import json
from functools import lru_cache

import numpy as np
import pytest

from helpers import mk
from rlcache.actions import decode_action, encode_action
from rlcache.analysis import pareto as P
from rlcache.analysis import report as R
from rlcache.baselines import policies as B
from rlcache.baselines.bounds import belady_bound
from rlcache.config import Config, LatencyConfig, StalenessConfig, WorkloadConfig
from rlcache.evaluation import WARMUP_FRAC, EvalContext, evaluate
from rlcache.results_schema import append_rows, validate_row
from rlcache.sim.engine import R_TRUNC, Insertion, Simulator
from rlcache.sim.policy import FixedActionPolicy
from rlcache.trace.oracle import annotate_oracle

WL = WorkloadConfig(n_requests=20_000, n_keys=300, write_interval_median_s=30_000.0)


# ---- Pareto utilities ---------------------------------------------------------------------------
def test_pareto_mask_and_dominates():
    s = np.array([0.00, 0.01, 0.02, 0.05, 0.03])
    h = np.array([0.50, 0.70, 0.72, 0.90, 0.60])
    assert P.pareto_mask(s, h).tolist() == [True, True, True, True, False]     # (0.03,.60) dominated
    assert P.dominates((0.01, 0.7), (0.03, 0.6)) and not P.dominates((0.03, 0.6), (0.01, 0.7))
    assert not P.dominates((0.01, 0.7), (0.01, 0.7))                          # equal: no strict gain


def test_envelope_is_concave_and_drops_dominated_by_chord():
    s = np.array([0.00, 0.01, 0.02, 0.05])
    h = np.array([0.50, 0.70, 0.72, 0.90])
    env = P.envelope(s, h)
    assert env.tolist() == [[0.0, 0.5], [0.01, 0.7], [0.05, 0.9]]   # (0.02, .72) is below the chord
    slopes = np.diff(env[:, 1]) / np.diff(env[:, 0])
    assert np.all(np.diff(slopes) <= 1e-12)
    assert P.envelope_ohr(env, 0.03) == (pytest.approx(0.8), False)
    assert P.envelope_ohr(env, 0.5) == (0.9, False)                # flat to the right
    assert P.envelope_ohr(env, -0.1)[1] is True                    # below every vertex -> flagged
    d, beyond = P.delta_ohr((0.03, 0.85), env)
    assert d == pytest.approx(0.05) and not beyond


# ---- policies ------------------------------------------------------------------------------------
def test_registry_is_the_frozen_list():
    reg = B.registry()
    names = [r.name for r in reg]
    assert len(names) == len(set(names)) == 71
    fam = {f: sum(r.family == f for r in reg) for f in {r.family for r in reg}}
    assert fam == {"fixed": 45, "random": 1, "stat_ttl": 6, "pred_ttl": 2, "aimd": 4,
                   "oracle_ttl": 2, "belady": 2, "place_hash": 3, "place_size": 3, "place_freq": 3}
    assert sum(r.policy_class == "heuristic" for r in reg) == 67
    assert sum(r.policy_class == "bound" for r in reg) == 4
    assert B.registry(include_bounds=False).__len__() == 67
    post = {r.family for r in reg if r.post_hoc}
    assert post == {"place_hash", "place_size", "place_freq"}          # Addendum M6-B, nothing else


class _Ctx:
    def __init__(self, key, ts=0.0, idx=0):
        self.key, self.ts, self.idx = key, ts, idx


def test_stat_ttl_snaps_in_log_space_and_defaults_to_3600():
    pol = B.StatTTLPolicy(np.array([np.nan, 7.0, 100.0, 2000.0]), B.REDIS)
    got = [decode_action(pol.decide(_Ctx(k))) for k in range(4)]
    assert [a.ttl_idx for a in got] == [4, 0, 2, 4]
    assert all(a.placement == B.REDIS and a.priority == 1 for a in got)


def _ins(stale=0, hits=0, reason="expiry", key=0):
    i = Insertion(1, key, 0, 0.0, encode_action(1, 2, 1), 100, 0, True)
    i.stale, i.hits_l2, i.close_reason = stale, hits, reason
    return i


def test_aimd_rules_and_bounds():
    p = B.AIMDPolicy(3, alpha_s=60.0, beta=0.5, start_s=120.0)
    p.on_close(_ins(hits=3, key=0))
    assert p.ttl[0] == 180.0                                   # clean insertion: +alpha
    p.on_close(_ins(stale=2, hits=5, key=1))
    assert p.ttl[1] == 60.0                                    # any stale read: x beta
    p.on_close(_ins(hits=0, key=2))
    assert p.ttl[2] == 120.0                                   # never re-read: unchanged
    p.on_close(_ins(stale=1, hits=1, key=0, reason=R_TRUNC))
    assert p.ttl[0] == 180.0                                   # censored closures ignored
    for _ in range(10):
        p.on_close(_ins(stale=1, key=1))
    assert p.ttl[1] == 5.0
    for _ in range(100):
        p.on_close(_ins(hits=1, key=2))
    assert p.ttl[2] == 3600.0
    assert decode_action(p.decide(_Ctx(2))).ttl_s == 3600


def test_zero_stale_oracle_ttl_buckets():
    nw = np.array([103.0, 3.0, np.inf, 120.0, 5.0, 40000.0])
    pol = B.ZeroStaleOracleTTL(nw, B.BOTH)
    idx = [decode_action(pol.decide(_Ctx(0, ts=3.0 if i == 1 else 0.0, idx=i))).ttl_idx
           for i in range(6)]
    # tnw = 103 -> 30 s ; 0 -> clamp 5 s ; inf -> 3600 ; 120 -> 120 ; 5 -> 5 ; 40000 -> 3600
    assert idx == [1, 0, 4, 2, 0, 4]


def test_hash_size_freq_placement_rules():
    h = B.HashPlacementPolicy(0.25)
    local = [decode_action(h.decide(_Ctx(k))).placement == 0 for k in range(4000)]
    assert 0.2 < np.mean(local) < 0.3
    assert local == [decode_action(h.decide(_Ctx(k))).placement == 0 for k in range(4000)]  # stable
    assert all(decode_action(h.decide(_Ctx(k))).ttl_s == 600 for k in range(20))
    s = B.SizePlacementPolicy(500.0)
    c = _Ctx(0)
    c.size = 500
    assert decode_action(s.decide(c)).placement == 0
    c.size = 501
    assert decode_action(s.decide(c)).placement == 1
    f = B.FreqPlacementPolicy(k=2, window=5)
    c = _Ctx(7)
    assert decode_action(f.decide(c)).placement == 1                      # unseen -> redis
    for i, key in enumerate([7, 1, 7, 2, 3]):
        f.on_request(i, float(i), key, False, False)
    assert decode_action(f.decide(c)).placement == 0                      # 2 hits in window
    f.on_request(5, 5.0, 4, False, False)                                 # evicts the first 7
    assert decode_action(f.decide(c)).placement == 1


def test_partitioning_rules_use_both_tiers_unlike_any_fixed_action():
    from rlcache.trace.synthetic import generate_synthetic
    tr = generate_synthetic(WorkloadConfig(n_requests=6000, n_keys=200,
                                           write_interval_median_s=50_000.0, seed=1))
    cfg = dataclasses.replace(Config(), latency=LatencyConfig(backend_sigma=0.0))
    res = {}
    for name, pol in (("fixed_redis", FixedActionPolicy.of(1, 3)), ("hash", B.HashPlacementPolicy(0.25))):
        sim = Simulator(tr, cfg, pol, l1_capacity_bytes=20_000, l2_capacity_bytes=200_000, seed=0)
        sim.begin(0, len(tr), 0)
        used = [0, 0]
        while (ctx := sim.next_decision()) is not None:
            sim.commit(pol.decide(ctx))
            used[0], used[1] = max(used[0], sim.l1.used), max(used[1], sim.l2.used)
        res[name] = tuple(used)
    assert res["fixed_redis"][0] == 0 and res["fixed_redis"][1] > 0       # strands L1
    assert res["hash"][0] > 0 and res["hash"][1] > 0                      # uses both


# ---- Belady bounds vs a brute-force optimum ------------------------------------------------------
def brute_opt(keys, is_write, C, ttl_constrained):
    n = len(keys)

    @lru_cache(maxsize=None)
    def go(i, cache):
        if i == n:
            return 0
        k = keys[i]
        if is_write[i]:
            if ttl_constrained and k in cache:
                return go(i + 1, cache - {k})
            return go(i + 1, cache)
        if k in cache:
            return 1 + go(i + 1, cache)
        best = go(i + 1, cache)                                 # bypass
        if len(cache) < C:
            best = max(best, go(i + 1, cache | {k}))
        else:
            for v in cache:
                best = max(best, go(i + 1, (cache - {v}) | {k}))
        return best

    return go(0, frozenset())


@pytest.mark.parametrize("ttl_constrained", [True, False])
@pytest.mark.parametrize("C", [1, 2, 3])
def test_belady_matches_brute_force_optimum(ttl_constrained, C):
    rng = np.random.default_rng(100 + C)
    for trial in range(25):
        n = 18
        keys = rng.integers(0, 5, n).tolist()
        wr = (rng.random(n) < 0.3).tolist()
        tr = mk([(float(i), keys[i], "w" if wr[i] else "r") for i in range(n)], n_keys=5)
        res = belady_bound(tr, annotate_oracle(tr), C, 0, n, 0, ttl_constrained)
        assert res["hits"] == brute_opt(tuple(keys), tuple(wr), C, ttl_constrained), (trial, keys, wr)


def test_belady_ttl_has_zero_stale_and_never_exceeds_plain_hits():
    tr = mk([(float(i), k, "w" if w else "r") for i, (k, w) in enumerate(
        zip([0, 1, 0, 2, 0, 1, 2, 0, 3, 0, 1], [0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0]))], n_keys=4)
    o = annotate_oracle(tr)
    a = belady_bound(tr, o, 2, 0, len(tr), 0, True)
    b = belady_bound(tr, o, 2, 0, len(tr), 0, False)
    assert a["stale"] == 0 and a["hits"] <= b["hits"]
    assert b["stale"] >= 0


def test_warmup_exclusion_in_belady():
    tr = mk([(float(i), 0, "r") for i in range(10)], n_keys=1)
    res = belady_bound(tr, annotate_oracle(tr), 1, 0, 10, 5, True)
    assert res["reads"] == 5 and res["hits"] == 5


def test_bound_is_valid_for_a_real_zero_stale_policy_on_unit_size_objects():
    """Equal object sizes -> Belady-TTL (capacity in objects) must upper-bound the simulator's OHR
    for a zero-stale policy with the same capacity (redis-only, perfect invalidation)."""
    from rlcache.trace.synthetic import generate_synthetic
    tr = generate_synthetic(WorkloadConfig(n_requests=15_000, n_keys=200,
                                           write_interval_median_s=8000.0, seed=3))
    tr = dataclasses.replace(tr, size=np.full(len(tr), 100, np.int32))
    C = 25
    cfg = dataclasses.replace(Config(), staleness=StalenessConfig("perfect"),
                              latency=LatencyConfig(backend_sigma=0.0))
    sim = Simulator(tr, cfg, FixedActionPolicy.of(1, 4), l1_capacity_bytes=100,
                    l2_capacity_bytes=C * 100, seed=0)
    m = sim.run(measure_from=1500)
    bound = belady_bound(tr, annotate_oracle(tr), C, 0, len(tr), 1500, True)
    assert m.n_stale == 0
    assert m.ohr() <= bound["ohr"] + 1e-9
    assert bound["ohr"] - m.ohr() < 0.5                          # and it is not vacuously loose


# ---- evaluation runner -----------------------------------------------------------------------------
@pytest.fixture(scope="module")
def ctx():
    return EvalContext.build(seed=4, capacity_frac=0.05, arm="harsh", workload=WL)


def _spec(name):
    return next(s for s in B.registry() if s.name == name)


def test_context_uses_fit_slice_only_and_equal_capacity(ctx):
    sp = ctx.splits
    assert sp.fit == (0, int(0.3 * len(ctx.trace))) and sp.test[1] == len(ctx.trace)
    assert ctx.predictor.meta["fit_end"] == sp.fit_end and not ctx.predictor.meta["uses_future"]
    assert ctx.l1_bytes + ctx.l2_bytes > 0 and ctx.l1_bytes == int(ctx.l2_bytes * 0.1)
    # scrambling the future leaves every fitted artifact unchanged
    rng = np.random.default_rng(0)
    key = ctx.trace.key.copy()
    key[sp.fit_end:] = rng.integers(0, ctx.trace.n_keys, len(key) - sp.fit_end)
    mutated = dataclasses.replace(ctx.trace, key=key)
    c2 = EvalContext.build(4, 0.05, "harsh", trace=mutated)
    assert np.array_equal(ctx.gap_stats.median, c2.gap_stats.median, equal_nan=True)
    assert np.array_equal(ctx.predictor.predicted_ttl, c2.predictor.predicted_ttl)


def test_slices_warmup_and_row_validity(ctx):
    for split in ("val", "test"):
        a, b, mf = ctx.slice_for(split)
        assert mf == a + int(WARMUP_FRAC * (b - a))
    assert ctx.slice_for("val")[1] <= ctx.slice_for("test")[0]
    row = evaluate(ctx, _spec("fixed:redis/600s/normal"), "test")
    validate_row(row)                                              # schema-valid
    a, b, mf = ctx.slice_for("test")
    n_reads_expected = int(ctx.trace.is_read[mf:b].sum())
    assert row["n_reads"] == n_reads_expected                       # warm-up excluded, nothing else
    assert row["n_fresh"] + row["n_stale"] + row["n_miss"] == row["n_reads"]
    assert row["split"] == "test" and row["data_source"] == "synthetic"
    assert row["share_redis"] == pytest.approx(1.0) and row["share_local"] == 0.0


def test_post_hoc_rows_are_labelled(ctx):
    r = evaluate(ctx, _spec("place_hash:0.25"), "test")
    assert r["notes"].startswith("post-hoc") and r["family"] == "place_hash"
    assert evaluate(ctx, _spec("fixed:redis/600s/normal"), "test")["notes"] == ""
    r2 = evaluate(ctx, _spec("place_freq:k3"), "val")                  # observer-driven policy runs
    assert 0.0 < r2["share_local"] < 1.0 and r2["n_reads"] > 0


def test_row_is_deterministic_and_utility_matches_definition(ctx):
    spec = _spec("stat_ttl:median/redis")
    r1, r2 = evaluate(ctx, spec, "val"), evaluate(ctx, spec, "val")
    for k in ("n_reads", "n_fresh", "n_stale", "n_miss", "ohr", "stale_read_rate", "utility",
              "cap_evictions_per_1k", "ttl_median_s"):
        assert r1[k] == r2[k]
    # recompute U from first principles with an independent simulator run
    a, b, mf = ctx.slice_for("val")
    sim = Simulator(ctx.trace, ctx.cfg, spec.make(ctx), l1_capacity_bytes=ctx.l1_bytes,
                    l2_capacity_bytes=ctx.l2_bytes, seed=ctx.seed)
    m = sim.run(a, b, mf)
    u = (m.n_hit + 0.5 * (m.lat_score_hits + m.lat_score_miss) - 3.0 * m.stale_cost) / m.n_reads
    assert r1["utility"] == pytest.approx(u)
    assert 0.0 < u < 3.0


def test_all_policies_share_the_same_capacity_and_zero_stale_bounds_hold(ctx):
    rows = {n: evaluate(ctx, _spec(n), "test") for n in
            ("zerostale_oracle_ttl:redis", "fixed:redis/3600s/normal", "random:45")}
    assert rows["zerostale_oracle_ttl:redis"]["n_stale"] == 0 or \
        rows["zerostale_oracle_ttl:redis"]["stale_read_rate"] < 0.01
    assert rows["fixed:redis/3600s/normal"]["stale_read_rate"] > \
        rows["zerostale_oracle_ttl:redis"]["stale_read_rate"]
    bel = evaluate(ctx, _spec("belady_ttl_constrained"), "test")
    assert bel["n_stale"] == 0 and bel["policy_class"] == "bound" and "capacity_objects" in bel["notes"]
    validate_row(bel)


def test_ttl_diagnostics_are_sensible(ctx):
    long = evaluate(ctx, _spec("fixed:redis/3600s/normal"), "test")
    short = evaluate(ctx, _spec("fixed:redis/5s/normal"), "test")
    assert long["ttl_median_s"] == 3600 and short["ttl_median_s"] == 5
    assert long["over_ttl_frac"] > short["over_ttl_frac"]           # long TTL outlives more writes
    assert 0.0 <= long["over_ttl_frac"] <= 1.0
    assert long["action_entropy_norm"] == 0.0                        # one action only


# ---- reporting --------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def tiny_results(tmp_path_factory):
    out = tmp_path_factory.mktemp("res") / "results.csv"
    wl = WorkloadConfig(n_requests=8_000, n_keys=150, write_interval_median_s=30_000.0)
    fams = {"fixed", "random", "stat_ttl", "oracle_ttl", "belady", "place_hash"}
    for seed in (0, 1):
        c = EvalContext.build(seed, 0.05, "harsh", workload=wl)
        rows = [evaluate(c, s, sp) for s in B.registry() if s.family in fams for sp in ("val", "test")]
        append_rows(out, rows)
    return out


def test_t2_selects_on_validation_and_reports_test(tiny_results):
    df = R.load_rows(tiny_results)
    sel = R.best_by_val(df, "harsh", 0.05)
    assert set(sel) == {"fixed", "random", "stat_ttl", "place_hash"}
    v = df[(df.split == "val") & (df.family == "fixed")]
    assert sel["fixed"] == v.groupby("policy").utility.mean().idxmax()
    t = R.t2_table(df, "harsh", 0.05)
    assert {"fixed", "random", "stat_ttl", "place_hash"} <= {p.split(" -> ")[0] for p in t.policy
                                                              if " -> " in p}
    assert (t["class"] == "bound").sum() == 4 and (t.seeds == 2).all()
    md = R.t2_markdown(t, "T2")
    assert "±" in md and "belady_ttl_constrained" in md


def test_frontier_and_paired_delta_and_figure(tiny_results, tmp_path):
    df = R.load_rows(tiny_results)
    fs = R.frontier_summary(df, "harsh", 0.05)
    assert fs["non_dominated"] and fs["envelope"] and len(fs["bounds"]) == 4
    # no bound may enter the frontier
    assert not any(r["policy"].startswith(("belady", "zerostale")) for r in fs["non_dominated"])
    d = R.paired_delta(df, "fixed:redis/600s/normal", "harsh", 0.05)
    assert len(d) == 2 and d.delta_ohr.notna().all()
    assert (d.delta_ohr <= 1e-9).all()                    # a baseline cannot beat its peers' envelope
    paths = R.write_reports(tiny_results, tmp_path, "harsh", [0.05])
    assert {p.suffix for p in paths} == {".md", ".csv", ".json", ".png"}
    assert all(p.exists() and p.stat().st_size > 0 for p in paths)
    assert json.loads((tmp_path / "frontier_harsh_cap0.05.json").read_text())["arm"] == "harsh"


def test_appending_twice_does_not_corrupt_header(tiny_results):
    n = len(R.load_rows(tiny_results))
    c = EvalContext.build(0, 0.05, "harsh", workload=WorkloadConfig(
        n_requests=8_000, n_keys=150, write_interval_median_s=30_000.0))
    append_rows(tiny_results, [evaluate(c, _spec("random:45"), "test")])
    assert len(R.load_rows(tiny_results)) == n + 1
