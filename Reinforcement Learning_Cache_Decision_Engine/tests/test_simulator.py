"""M4 gate: simulator mechanisms on hand-computed micro-traces + invariants on a synthetic run.

Micro-trace conventions: ttl_idx 1 = 30 s, 2 = 120 s, 4 = 3600 s; placement 0 local, 1 redis,
2 both; the backend fetch window is 8 ms, so a value fetched at t is visible from t + 0.008.
"""
import dataclasses

import numpy as np
import pytest

from rlcache.config import (CacheConfig, Config, LatencyConfig, StalenessConfig, WorkloadConfig)

FLAT = LatencyConfig(backend_sigma=0.0)          # exact 8 ms fetch windows in micro-traces
from rlcache.sim import engine as E
from rlcache.sim.engine import Simulator, resolve_capacities
from rlcache.sim.policy import FixedActionPolicy, RandomPolicy, SequencePolicy
from rlcache.actions import encode_action
from rlcache.trace.record import OP_CODE, Trace
from rlcache.trace.synthetic import generate_synthetic

LOCAL, REDIS, BOTH = 0, 1, 2
BIG = 10**9


def mk(rows, size=100, n_keys=None):
    """rows: (t, key, 'r'|'w'[, size])"""
    ts = [r[0] for r in rows]
    key = [r[1] for r in rows]
    op = [OP_CODE["get"] if r[2] == "r" else OP_CODE["set"] for r in rows]
    sz = [r[3] if len(r) > 3 else size for r in rows]
    n = len(rows)
    return Trace(np.array(ts, float), np.array(key, np.int64), np.array(sz, np.int32),
                 np.zeros(n, np.int32), np.array(op, np.int8), np.zeros(n, np.int32),
                 n_keys or (max(key) + 1))


def cfg_with(mode="perfect", p_inv_l1=1.0, d=0.0, p_bypass=0.0, **cache_kw):
    c = dataclasses.replace(Config(), latency=FLAT)
    cache = dataclasses.replace(c.cache, **cache_kw) if cache_kw else c.cache
    return dataclasses.replace(c, staleness=StalenessConfig(mode, p_inv_l1, d, p_bypass), cache=cache)


def run(trace, policy, cfg=None, l1=BIG, l2=BIG, seed=0, **kw):
    sim = Simulator(trace, cfg or cfg_with(), policy, l1_capacity_bytes=l1, l2_capacity_bytes=l2,
                    seed=seed, check_invariants=True, **kw)
    sim.run()
    return sim


def closed_by_key(sim, key):
    return [i for i in sim.closed if i.key == key]


# ---- basic lookup, accounting ----------------------------------------------------------------
def test_miss_then_fresh_l2_hit_and_byte_seconds():
    sim = run(mk([(0, 0, "r"), (1, 0, "r")]), FixedActionPolicy.of(REDIS, 1))
    m = sim.metrics
    assert (m.n_reads, m.n_miss, m.fresh_l2, m.fresh_l1, m.n_stale) == (2, 1, 1, 0, 0)
    assert m.n_decisions == 1 and m.backend_fetches == 1
    (ins,) = sim.closed
    assert ins.close_reason == E.R_TRUNC and ins.hits_l2 == 1 and ins.fresh == 1
    assert ins.byte_seconds == pytest.approx(100 * (1 - 0.008))
    assert ins.t_materialize == pytest.approx(0.008)


def test_fresh_stale_miss_partition_reads():
    sim = run(mk([(0, 0, "r"), (1, 0, "r"), (2, 1, "r"), (3, 0, "w"), (4, 0, "r")]),
              FixedActionPolicy.of(BOTH, 2), cfg=cfg_with("ttl_only"))
    m = sim.metrics
    assert m.n_fresh + m.n_stale + m.n_miss == m.n_reads == 4
    assert m.n_writes == 1 and m.backend_writes == 1


def test_expiry_is_exact_and_counted_as_ttl_expiration_not_eviction():
    sim = run(mk([(0, 0, "r"), (29, 0, "r"), (31, 0, "r")]), FixedActionPolicy.of(REDIS, 1))
    first = sim.closed[0]
    assert first.close_reason == E.R_EXPIRY
    assert first.close_time == pytest.approx(30.008)
    assert first.byte_seconds == pytest.approx(100 * 30.0)
    assert first.hits == 1
    assert sim.metrics.ttl_expirations == 1 and sim.metrics.cap_evictions == 0   # R-S13
    assert sim.metrics.n_miss == 2 and sim.metrics.n_decisions == 2             # re-fetched


def test_never_read_entry_still_expires_at_its_expiry_time():
    """R-S7: expiry is a terminal event even if the key is never re-read."""
    sim = run(mk([(0, 0, "r"), (100, 1, "r")]), FixedActionPolicy.of(REDIS, 1))
    ins0 = [i for i in sim.closed if i.key == 0][0]
    assert ins0.close_reason == E.R_EXPIRY and ins0.close_time == pytest.approx(30.008)
    assert ins0.hits == 0


# ---- placement semantics (C-2) ---------------------------------------------------------------
@pytest.mark.parametrize("placement,l1_used,l2_used", [(LOCAL, True, False), (REDIS, False, True),
                                                       (BOTH, True, True)])
def test_placement_writes_the_right_tiers(placement, l1_used, l2_used):
    tr = mk([(0, 0, "r"), (1, 1, "r")])
    sim = Simulator(tr, cfg_with(), FixedActionPolicy.of(placement, 4), seed=0)
    sim.begin()
    ctx = sim.next_decision()                    # request 0 misses -> decision pending
    assert ctx.key == 0 and sim.l1.used == sim.l2.used == 0
    sim.commit(encode_action(placement, 4, 1))
    ctx = sim.next_decision()                    # request 1: fetch of key 0 has landed by t = 1
    assert ctx.key == 1
    assert (sim.l1.used > 0) == l1_used and (sim.l2.used > 0) == l2_used


def test_manual_driver_matches_run_and_enforces_protocol():
    tr = generate_synthetic(WorkloadConfig(n_requests=6000, n_keys=200, write_interval_median_s=60000.0, seed=4))
    a = Simulator(tr, Config(), RandomPolicy(2), seed=1)
    a.run()
    pol = RandomPolicy(2)
    b = Simulator(tr, Config(), pol, seed=1)
    b.begin()
    n = 0
    while (ctx := b.next_decision()) is not None:
        with pytest.raises(RuntimeError):
            b.next_decision()                    # must commit first
        b.commit(pol.decide(ctx))
        n += 1
        if n > 3:
            break                                # protocol check done; finish with run-style loop
    while (ctx := b.next_decision()) is not None:
        b.commit(pol.decide(ctx))
    assert (a.metrics.n_fresh, a.metrics.n_stale, a.metrics.n_miss, a.metrics.cap_evictions) == (
        b.metrics.n_fresh, b.metrics.n_stale, b.metrics.n_miss, b.metrics.cap_evictions)
    assert a.n_closed == b.n_closed and a.n_created == b.n_created
    with pytest.raises(RuntimeError):
        b.commit(0)                              # nothing pending


def test_per_key_backend_latency_varies_and_is_seeded():
    tr = mk([(0, 0, "r"), (0, 1, "r"), (0, 2, "r")])
    c = dataclasses.replace(Config(), latency=LatencyConfig(backend_sigma=0.5, seed=7))
    s1 = Simulator(tr, c, FixedActionPolicy.of(REDIS, 1))
    s2 = Simulator(tr, c, FixedActionPolicy.of(REDIS, 1))
    s3 = Simulator(tr, dataclasses.replace(c, latency=LatencyConfig(backend_sigma=0.5, seed=8)),
                   FixedActionPolicy.of(REDIS, 1))
    assert s1.key_backend_s == s2.key_backend_s and s1.key_backend_s != s3.key_backend_s
    assert len(set(round(x, 9) for x in s1.key_backend_s)) == 3          # differ across keys
    big = Simulator(generate_synthetic(WorkloadConfig(n_requests=3000, n_keys=2000, write_interval_median_s=1e9, seed=0)),
                    c, FixedActionPolicy.of(REDIS, 1))
    assert np.mean(big.key_backend_s) == pytest.approx(0.008, rel=0.1)    # lognormal mean 1


def test_on_decision_hook_and_observer_see_every_request():
    class Obs:
        def __init__(self): self.rows = []
        def on_request(self, i, t, k, is_write, hit): self.rows.append((i, is_write, hit))

    class P(FixedActionPolicy):
        def __init__(self): super().__init__(encode_action(REDIS, 2, 1)); self.ins = []
        def on_decision(self, ins): self.ins.append(ins.id)

    o, p = Obs(), P()
    tr = mk([(0, 0, "r"), (1, 0, "r"), (2, 0, "w"), (3, 0, "r")])
    Simulator(tr, cfg_with("ttl_only"), p, observer=o).run()
    assert [r[0] for r in o.rows] == [0, 1, 2, 3]
    assert [r[2] for r in o.rows] == [False, True, None, True]      # miss, hit, (write), stale hit
    assert p.ins == [1]


def test_local_placement_hits_l1_only():
    sim = run(mk([(0, 0, "r"), (1, 0, "r")]), FixedActionPolicy.of(LOCAL, 2))
    assert sim.metrics.fresh_l1 == 1 and sim.metrics.fresh_l2 == 0


# ---- staleness model (C-6, D-20) -----------------------------------------------------------------
def test_perfect_invalidation_removes_copy_and_next_read_misses():
    sim = run(mk([(0, 0, "r"), (1, 0, "w"), (2, 0, "r")]), FixedActionPolicy.of(BOTH, 2))
    m = sim.metrics
    assert m.n_stale == 0 and m.n_miss == 2
    assert m.invalidations == 2                       # both copies
    assert sim.closed[0].close_reason == E.R_INVAL and sim.closed[0].close_time == pytest.approx(1.0)


def test_ttl_only_serves_stale_with_correct_age_and_cost():
    sim = run(mk([(0, 0, "r"), (10, 0, "w"), (15, 0, "r")]), FixedActionPolicy.of(REDIS, 1),
              cfg=cfg_with("ttl_only"))
    m = sim.metrics
    assert (m.n_stale, m.stale_l2, m.n_miss) == (1, 1, 1)
    assert m.stale_ages == [pytest.approx(5.0)]       # superseded at t=10, read at t=15
    ins = sim.closed[0]
    assert ins.stale == 1 and ins.stale_age_sum == pytest.approx(5.0)
    assert ins.stale_cost_sum == pytest.approx(5.0 / 30.0)       # min(1, age / ttl_chosen)
    assert m.stale_read_rate() == pytest.approx(0.5)


def test_stale_age_measures_time_since_FIRST_superseding_write():
    sim = run(mk([(0, 0, "r"), (10, 0, "w"), (12, 0, "w"), (20, 0, "r")]),
              FixedActionPolicy.of(REDIS, 1), cfg=cfg_with("ttl_only"))
    assert sim.metrics.stale_ages == [pytest.approx(10.0)]


def test_lossy_l1_delayed_invalidation_window_is_stale_then_gone():
    cfg = cfg_with("lossy", p_inv_l1=1.0, d=2.0, p_bypass=0.0)
    sim = run(mk([(0, 0, "r"), (10, 0, "w"), (11, 0, "r"), (13, 0, "r")]),
              FixedActionPolicy.of(BOTH, 2), cfg=cfg)
    m = sim.metrics
    assert m.stale_l1 == 1 and m.stale_ages == [pytest.approx(1.0)]   # in the 2 s propagation gap
    assert m.n_miss == 2                                              # t=13: both tiers gone


def test_redis_only_with_synchronous_l2_invalidation_never_stale():
    cfg = cfg_with("lossy", p_inv_l1=0.0, d=0.0, p_bypass=0.0)
    sim = run(mk([(0, 0, "r"), (10, 0, "w"), (11, 0, "r")]), FixedActionPolicy.of(REDIS, 2), cfg=cfg)
    assert sim.metrics.n_stale == 0 and sim.metrics.n_miss == 2


def test_local_only_with_lost_l1_invalidation_is_stale_until_ttl():
    """The placement x TTL coupling: a sidecar-only copy of a volatile key is how stale data
    reaches the user (MD)."""
    cfg = cfg_with("lossy", p_inv_l1=0.0, d=0.0, p_bypass=0.0)
    sim = run(mk([(0, 0, "r"), (10, 0, "w"), (11, 0, "r"), (200, 0, "r")]),
              FixedActionPolicy.of(LOCAL, 2), cfg=cfg)                 # ttl 120 s
    m = sim.metrics
    assert m.stale_l1 == 1 and m.n_miss == 2                           # t=200 > expiry at 120.008


def test_bypass_makes_even_redis_stale():
    cfg = cfg_with("lossy", p_inv_l1=1.0, d=0.0, p_bypass=1.0)
    sim = run(mk([(0, 0, "r"), (10, 0, "w"), (11, 0, "r")]), FixedActionPolicy.of(REDIS, 2), cfg=cfg)
    assert sim.metrics.n_stale == 1


def test_write_during_fetch_arrives_stale_in_ttl_only_mode():
    sim = run(mk([(0.0, 0, "r"), (0.004, 0, "w"), (1.0, 0, "r")]), FixedActionPolicy.of(REDIS, 2),
              cfg=cfg_with("ttl_only"))
    assert sim.metrics.n_stale == 1
    assert sim.metrics.stale_ages == [pytest.approx(1.0 - 0.004)]


def test_perfect_mode_drops_value_that_went_stale_during_fetch():
    """Perfect invalidation must give stale == 0 even for the fetch/write race (D-25)."""
    sim = run(mk([(0.0, 0, "r"), (0.004, 0, "w"), (1.0, 0, "r")]), FixedActionPolicy.of(REDIS, 2))
    assert sim.metrics.n_stale == 0 and sim.metrics.n_miss == 2
    assert sim.closed[0].close_reason == E.R_INVAL and sim.closed[0].n_copies_made == 0


# ---- stampede / in-flight (C-20) ----------------------------------------------------------------------
def test_concurrent_misses_inside_fetch_window_are_real_misses_one_decision():
    tr = mk([(0.0, 0, "r"), (0.004, 0, "r"), (0.02, 0, "r")])
    sim = run(tr, FixedActionPolicy.of(REDIS, 2))
    m = sim.metrics
    assert (m.n_miss, m.fresh_l2, m.n_decisions, m.backend_fetches) == (2, 1, 1, 2)
    assert m.concurrent_fetches == 1
    assert sim.closed[0].concurrent == 2


def test_inflight_counts_open_fetch_windows():
    seen = []

    class Probe:
        def decide(self, ctx):
            seen.append((ctx.key, ctx.sim.inflight(ctx.ts)))
            return encode_action(REDIS, 2, 1)

    run(mk([(0.0, 0, "r"), (0.004, 0, "r"), (0.005, 1, "r"), (0.1, 2, "r")]), Probe())
    assert seen == [(0, 0), (1, 2), (2, 0)]      # k1's decision sees k0's two open fetches


# ---- capacity, eviction, priority (R-S10, R-S11) -----------------------------------------------------------
def test_capacity_eviction_closes_insertion_and_is_counted_separately():
    tr = mk([(0, 0, "r"), (1, 1, "r"), (2, 2, "r"), (3, 0, "r")])
    sim = run(tr, FixedActionPolicy.of(REDIS, 4), l2=250)
    assert sim.l2.used <= 250
    assert sim.metrics.cap_evictions >= 1 and sim.metrics.ttl_expirations == 0
    assert any(i.close_reason == E.R_EVICTION for i in sim.closed)


def test_priority_high_protects_an_older_entry():
    # k0 inserted at t=0 (high), k1 at t=5 (normal), k2 at t=20 forces one eviction
    rows = [(0, 0, "r"), (5, 1, "r"), (20, 2, "r"), (21, 2, "r")]   # trailing hit: k2 has landed
    hi, norm = encode_action(REDIS, 4, 2), encode_action(REDIS, 4, 1)
    sim = run(mk(rows), SequencePolicy([hi, norm, norm]), l2=250)
    evicted = [i.key for i in sim.closed if i.close_reason == E.R_EVICTION]
    assert evicted == [1]                          # idle 15 vs (idle 20 / 2 = 10)
    sim = run(mk(rows), SequencePolicy([norm, norm, norm]), l2=250)
    evicted = [i.key for i in sim.closed if i.close_reason == E.R_EVICTION]
    assert evicted == [0]                          # without protection the older entry goes


def test_priority_low_makes_a_younger_entry_the_victim():
    # k0 (normal) @0, k1 (low) @3, k2 forces eviction @8:
    #   idle(k0) = 8.0 -> score 8.0 ;  idle(k1) = 5.0 / 0.5 = 10.0  -> the YOUNGER low-priority goes
    rows = [(0, 0, "r"), (3, 1, "r"), (8, 2, "r"), (9, 2, "r")]
    norm, low = encode_action(REDIS, 4, 1), encode_action(REDIS, 4, 0)
    sim = run(mk(rows), SequencePolicy([norm, low, norm]), l2=250)
    assert [i.key for i in sim.closed if i.close_reason == E.R_EVICTION] == [1]
    sim = run(mk(rows), SequencePolicy([norm, norm, norm]), l2=250)
    assert [i.key for i in sim.closed if i.close_reason == E.R_EVICTION] == [0]


def test_object_larger_than_tier_is_rejected_and_closed_once():
    sim = run(mk([(0, 0, "r", 5000), (1, 0, "r", 5000), (2, 0, "r", 5000)]),
              FixedActionPolicy.of(REDIS, 2), l2=1000)
    assert sim.metrics.rejected == 2 and sim.metrics.n_miss == 3
    assert [i.close_reason for i in sim.closed] == [E.R_REJECTED, E.R_REJECTED, E.R_TRUNC]
    assert sim.n_closed == sim.n_created == 3


def test_promotion_flag_controls_placement_collapse():
    rows = [(0, 0, "r"), (1, 0, "r"), (2, 0, "r")]
    off = run(mk(rows), FixedActionPolicy.of(REDIS, 2), cfg=cfg_with())
    assert (off.metrics.fresh_l1, off.metrics.fresh_l2) == (0, 2)
    on = run(mk(rows), FixedActionPolicy.of(REDIS, 2), cfg=cfg_with(promote_on_l2_hit=True))
    assert (on.metrics.fresh_l1, on.metrics.fresh_l2) == (1, 1)          # C-36: redis -> both


def test_hard_cap_closes_long_lived_insertion():
    sim = run(mk([(0, 0, "r"), (500, 1, "r")]), FixedActionPolicy.of(REDIS, 4),
              cfg=cfg_with(hard_cap_s=100.0))
    ins = [i for i in sim.closed if i.key == 0][0]
    assert ins.close_reason == E.R_HARDCAP and ins.close_time == pytest.approx(100.0)


def test_no_hard_cap_events_in_default_config():
    """Max lifetime (3600 s TTL + fetch) < 7200 s cap, so the cap is purely a safety net."""
    tr = generate_synthetic(WorkloadConfig(n_requests=20_000, n_keys=300, seed=1))
    sim = Simulator(tr, dataclasses.replace(Config(), latency=FLAT), RandomPolicy(1), l1_capacity_bytes=BIG, l2_capacity_bytes=BIG)
    sim.run()
    assert all(i.close_reason != E.R_HARDCAP for i in sim.closed)
    done = [i for i in sim.closed if i.close_reason != E.R_TRUNC]
    assert max(i.lifetime_s for i in done) <= 3600 + 0.008 + 1e-6


# ---- warm-up exclusion -----------------------------------------------------------------------------------------
def test_measure_from_excludes_warmup_but_keeps_state():
    tr = mk([(0, 0, "r"), (1, 0, "r"), (2, 0, "r"), (3, 0, "r")])
    sim = Simulator(tr, cfg_with(), FixedActionPolicy.of(REDIS, 2), l1_capacity_bytes=BIG,
                    l2_capacity_bytes=BIG)
    m = sim.run(measure_from=2)
    assert m.n_reads == 2 and m.n_miss == 0 and m.fresh_l2 == 2     # state carried over


# ---- timestamp ties ---------------------------------------------------------------------------------------------
def test_spread_equal_timestamps_preserves_order_and_stays_in_slot():
    tr = mk([(0, 0, "r"), (0, 1, "r"), (0, 2, "r"), (1, 0, "r"), (1, 1, "r"), (5, 0, "r")])
    sp = tr.with_spread_timestamps()
    assert np.all(np.diff(sp.ts) > 0)                              # strictly increasing now
    assert np.array_equal(sp.key, tr.key)
    assert np.all((sp.ts >= tr.ts) & (sp.ts < tr.ts + 1.0))
    assert sp.ts[2] < 1.0 <= sp.ts[3] < 2.0
    assert sp.meta["spread_timestamps"] is True


def test_spread_timestamps_removes_false_same_second_stampede():
    rows = [(0, 0, "r")] * 6                                        # six reads in the same second
    tr = mk(rows)
    a = run(tr, FixedActionPolicy.of(REDIS, 2))
    b = run(tr.with_spread_timestamps(), FixedActionPolicy.of(REDIS, 2))
    assert a.metrics.concurrent_fetches == 5                        # all look concurrent
    assert b.metrics.concurrent_fetches < 5 and b.metrics.fresh_l2 >= 1


# ---- capacity sizing ------------------------------------------------------------------------------------------
def test_resolve_capacities_from_footprint():
    tr = mk([(0, 0, "r", 1000), (1, 1, "r", 3000)])
    l1, l2 = resolve_capacities(tr, CacheConfig(l2_footprint_frac=0.5, l1_fraction_of_l2=0.1))
    assert l2 == 2000 and l1 == 200
    l1, l2 = resolve_capacities(tr, CacheConfig(l2_capacity_bytes=5000))
    assert l2 == 5000 and l1 == 500


# ---- invariants on a full synthetic run (the M4 gate) ---------------------------------------------------------
@pytest.fixture(scope="module")
def syn():
    cfg = WorkloadConfig(n_requests=60_000, n_keys=600, write_interval_median_s=12000.0, seed=2)
    return generate_synthetic(cfg)


def _sim(tr, policy, st=None, seed=0, l2_frac=0.05, **kw):
    cfg = dataclasses.replace(Config(), latency=FLAT)
    if st is not None:
        cfg = dataclasses.replace(cfg, staleness=st)
    cfg = dataclasses.replace(cfg, cache=dataclasses.replace(cfg.cache, l2_footprint_frac=l2_frac))
    sim = Simulator(tr, cfg, policy, seed=seed, check_invariants=True, **kw)
    sim.run()
    return sim


def test_every_insertion_is_closed_exactly_once(syn):
    sim = _sim(syn, RandomPolicy(3))
    ids = [i.id for i in sim.closed]
    assert len(ids) == len(set(ids)) == sim.n_created == sim.n_closed
    assert not sim.open and all(i.closed for i in sim.closed)
    assert sim.metrics.n_decisions == sim.n_created           # no warm-up -> all measured


def test_counts_partition_reads_and_match_trace(syn):
    sim = _sim(syn, RandomPolicy(3))
    m = sim.metrics
    assert m.n_fresh + m.n_stale + m.n_miss == m.n_reads == int(syn.is_read.sum())
    assert m.n_writes == int(syn.is_write.sum())
    assert m.backend_fetches == m.n_miss                      # one fetch per missing read (R-S14)
    # per-insertion hit accounting agrees with the global counters
    assert sum(i.hits for i in sim.closed) == m.n_hit
    assert sum(i.stale for i in sim.closed) == m.n_stale


def test_byte_usage_never_exceeds_capacity(syn):
    sim = _sim(syn, FixedActionPolicy.of(BOTH, 4, 2), l2_frac=0.01)   # heavy pressure
    assert sim.metrics.cap_evictions > 0
    # invariants (used <= cap, used == sum(sizes)) were asserted every 64 requests by the run itself


def test_deterministic_under_seed_and_sensitive_to_it(syn):
    a = _sim(syn, RandomPolicy(5), seed=11)
    b = _sim(syn, RandomPolicy(5), seed=11)
    c = _sim(syn, RandomPolicy(5), seed=12)
    sig = lambda s: (s.metrics.n_fresh, s.metrics.n_stale, s.metrics.n_miss, s.metrics.cap_evictions,
                     [(i.id, i.close_reason, round(i.close_time, 6)) for i in s.closed][:2000])
    assert sig(a) == sig(b)
    assert sig(a) != sig(c)


def test_perfect_invalidation_has_zero_stale_reads(syn):
    for pol in (FixedActionPolicy.of(LOCAL, 4), FixedActionPolicy.of(BOTH, 4), RandomPolicy(1)):
        sim = _sim(syn, pol, st=StalenessConfig("perfect"))
        assert sim.metrics.n_stale == 0 and sim.metrics.n_hit > 0


def test_ttl_only_has_stale_reads_and_they_grow_with_ttl(syn):
    st = StalenessConfig("ttl_only")
    rates, ohrs = [], []
    for t in (0, 2, 4):                                       # 5 s, 120 s, 3600 s
        sim = _sim(syn, FixedActionPolicy.of(BOTH, t), st=st, l2_frac=0.2)
        rates.append(sim.metrics.stale_read_rate())
        ohrs.append(sim.metrics.ohr())
    assert rates == sorted(rates) and rates[-1] > rates[0] + 0.005
    assert ohrs == sorted(ohrs)                               # longer TTL -> more hits


def test_lossy_stale_reads_only_come_from_the_fetch_write_race_when_invalidation_is_instant(syn):
    st = StalenessConfig("lossy", p_inv_l1=1.0, d_inv_l1_s=0.0, p_bypass=0.0)
    sim = _sim(syn, FixedActionPolicy.of(BOTH, 4), st=st, l2_frac=0.2)
    stale_ins = [i for i in sim.closed if i.stale > 0]
    assert all(i.write_during_fetch_t is not None for i in stale_ins)
    loose = _sim(syn, FixedActionPolicy.of(BOTH, 4), st=StalenessConfig("ttl_only"), l2_frac=0.2)
    assert sim.metrics.n_stale <= 0.05 * max(loose.metrics.n_stale, 1)


def test_redis_placement_is_safer_than_local_under_lossy_invalidation(syn):
    st = StalenessConfig("lossy", p_inv_l1=0.3, d_inv_l1_s=5.0, p_bypass=0.0)
    loc = _sim(syn, FixedActionPolicy.of(LOCAL, 4), st=st, l2_frac=0.3)
    red = _sim(syn, FixedActionPolicy.of(REDIS, 4), st=st, l2_frac=0.3)
    assert loc.metrics.stale_read_rate() > red.metrics.stale_read_rate()


def test_expired_insertions_close_exactly_ttl_after_materialization(syn):
    sim = _sim(syn, RandomPolicy(9), st=StalenessConfig("ttl_only"))
    single = [i for i in sim.closed
              if i.close_reason == E.R_EXPIRY and i.n_copies_made == 1 and i.first_reason == E.R_EXPIRY]
    assert len(single) > 100
    for i in single[:500]:
        assert i.close_time - i.t_materialize == pytest.approx(i.ttl_s, abs=1e-6)


def test_stale_age_is_bounded_by_ttl_plus_fetch_window(syn):
    sim = _sim(syn, RandomPolicy(2), st=StalenessConfig("ttl_only"))
    worst = max(sim.metrics.stale_ages)
    assert worst <= 3600 + 0.008 + 1e-6
    assert all(0 <= a for a in sim.metrics.stale_ages)


def test_throughput_is_logged(syn):
    sim = _sim(syn, FixedActionPolicy.of(REDIS, 2))
    assert len(sim.metrics.throughput) >= 1 and all(r > 0 for _, r in sim.metrics.throughput)
