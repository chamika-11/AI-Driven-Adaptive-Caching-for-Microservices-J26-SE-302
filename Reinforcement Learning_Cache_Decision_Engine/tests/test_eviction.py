"""Addendum M11-E (E1): LRU / FIFO / SIEVE / S3-FIFO evictors on hand-traced scenarios, plus engine integration."""
import dataclasses
from types import SimpleNamespace

import numpy as np
import pytest

from rlcache.actions import encode_action
from rlcache.config import CacheConfig, Config, LatencyConfig, StalenessConfig
from rlcache.sim import eviction as EV
from rlcache.sim.engine import Simulator
from rlcache.sim.policy import FixedActionPolicy
from tests.helpers import mk


def C(k, size=1):
    return SimpleNamespace(key=k, size=size)


# ---- unit scenarios --------------------------------------------------------------------------
def test_lru_and_fifo_order():
    for cls, expect in ((EV.LRUEvictor, "B"), (EV.FIFOEvictor, "A")):
        e = cls(3)
        cs = {k: C(k) for k in "ABC"}
        for k in "ABC":
            e.on_insert(cs[k])
        e.on_hit(cs["A"])
        assert e.victim().key == expect


def test_sieve_hand_sweeps_and_clears_visited_bits():
    e = EV.SieveEvictor(3)
    cs = {k: C(k) for k in "ABCD"}
    for k in "ABC":
        e.on_insert(cs[k])                 # oldest A ... newest C
    e.on_hit(cs["A"])                      # A visited
    v = e.victim()
    assert v.key == "B" and e.visited["A"] is False       # A got its second chance (bit cleared), B evicted
    e.on_remove(v)
    assert e.hand == "C"                                  # hand moved to B's newer neighbour
    e.on_insert(cs["D"])                                  # order oldest->newest: A, C, D
    v = e.victim()
    assert v.key == "C"                                   # hand continues at C, NOT from the tail
    e.on_remove(v)
    assert e.hand == "D"
    v = e.victim(); assert v.key == "D"; e.on_remove(v)
    assert e.hand is None
    assert e.victim().key == "A"                          # wraps to the oldest object


def test_sieve_new_objects_start_unvisited_and_removals_relink():
    e = EV.SieveEvictor(10)
    cs = {k: C(k) for k in "ABC"}
    for k in "ABC":
        e.on_insert(cs[k])
    e.on_remove(cs["B"])                                  # expiry / invalidation of a middle object
    assert e.older["C"] == "A" and e.newer["A"] == "C" and e.tail == "A" and e.head == "C"
    e.on_remove(cs["A"]); e.on_remove(cs["C"])
    assert e.head is None and e.tail is None and not e.obj


def test_s3fifo_ghost_promotion_and_main_reinsertion():
    e = EV.S3FIFOEvictor(cap=10)                          # small target = 1 byte
    a, b = C("A"), C("B")
    e.on_insert(a); e.on_insert(b)
    v = e.victim()
    assert v.key == "A" and "A" in e.ghost                # freq 0 in S -> evicted, remembered in the ghost
    e.on_remove(v)
    a2 = C("A")
    e.on_insert(a2)
    assert "A" in e.main and "A" not in e.ghost           # ghost hit -> straight to M
    e.on_hit(b); e.on_hit(b)                              # B freq 2 > 1
    v = e.victim()
    assert "B" in e.main and e.freq["B"] == 0             # promoted S -> M with frequency reset
    assert v.key == "A"                                   # A (freq 0) is first in M and is evicted
    e.on_remove(v)
    e2 = EV.S3FIFOEvictor(cap=10)
    x, y = C("X"), C("Y")
    e2.ghost["X"] = 1; e2.ghost["Y"] = 1; e2.ghost_bytes = 2
    e2.on_insert(x); e2.on_insert(y)                      # both go to M
    e2.on_hit(x)
    assert e2.victim().key == "Y" and e2.freq["X"] == 0   # X reinserted with freq - 1, Y evicted


def test_s3fifo_ghost_is_bounded_in_bytes():
    e = EV.S3FIFOEvictor(cap=10)
    for i in range(50):
        e._ghost_add(i, 2)
    assert e.ghost_bytes <= 9 and e.ghost_bytes == sum(e.ghost.values())


# ---- engine integration ----------------------------------------------------------------------
FLAT = LatencyConfig(backend_sigma=0.0)


def _cfg(kind):
    c = dataclasses.replace(Config(), latency=FLAT, staleness=StalenessConfig("perfect", 1.0, 0.0, 0.0))
    return dataclasses.replace(c, cache=dataclasses.replace(c.cache, base_eviction=kind))


def _residents_at_last_decision(kind):
    rows = [(0, "A"), (1, "B"), (2, "A"), (3, "C"), (10, "D")]
    keymap = {"A": 0, "B": 1, "C": 2, "D": 3}
    tr = mk([(t, keymap[k], "r") for t, k in rows], size=100)
    snap = {}

    class Pol:
        def decide(self, ctx):
            snap["res"] = set(ctx.sim.l2.entries)
            return encode_action(1, 4, 1)                       # redis, 3600 s, normal
    sim = Simulator(tr, _cfg(kind), Pol(), l1_capacity_bytes=10**9, l2_capacity_bytes=200, seed=0,
                    check_invariants=True)
    sim.run()
    return snap["res"], sim


@pytest.mark.parametrize("kind,expect", [("fifo", {1, 2}), ("lru", {0, 2}), ("sieve", {0, 2}), ("s3fifo", {1, 2})])   # S3-FIFO: one hit (freq 1) is not > 1, so A is not promoted out of S
def test_engine_eviction_choice_on_micro_trace(kind, expect):
    res, sim = _residents_at_last_decision(kind)
    assert res == expect, (kind, res)


def test_default_sampled_lru_is_unchanged_by_the_hooks():
    res, _ = _residents_at_last_decision("sampled_lru")
    assert res == {0, 2}                                         # exact on a 2-entry tier (all sampled)
    with pytest.raises(ValueError):
        Simulator(mk([(0, 0, "r")]), _cfg("nonsense"), FixedActionPolicy.of(1, 1))


@pytest.mark.parametrize("kind", ["lru", "fifo", "sieve", "s3fifo"])
def test_invariants_and_capacity_on_a_random_trace(kind):
    from rlcache.config import WorkloadConfig
    from rlcache.sim.policy import RandomPolicy
    from rlcache.trace.synthetic import generate_synthetic
    tr = generate_synthetic(WorkloadConfig(n_requests=20_000, n_keys=300, write_interval_median_s=20_000.0, seed=2))
    cfg = _cfg(kind)
    sim = Simulator(tr, cfg, RandomPolicy(1), l1_capacity_bytes=4_000, l2_capacity_bytes=40_000, seed=1,
                    check_invariants=True)
    m = sim.run()
    assert m.cap_evictions > 100 and 0.0 < m.ohr() < 1.0
    # the evictor's bookkeeping equals the tier's contents at every checkpoint (final state is empty after finalize)
    for tid, ev in sim._ev.items():
        tier = sim.l1 if tid == 0 else sim.l2
        assert tier.used == 0 and len(tier.entries) == 0
