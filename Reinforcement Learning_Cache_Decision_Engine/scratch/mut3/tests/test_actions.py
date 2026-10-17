"""M1 gate: exhaustive round-trip over all 45 actions, stride order, bounds, ablation helpers."""
import itertools

import numpy as np
import pytest

from rlcache import actions as A
from rlcache.config import N_ACTIONS, N_PLACE, N_PRIO, N_TTL, TTL_BUCKETS_S


def test_space_is_exactly_45():
    assert N_ACTIONS == 45 == N_PLACE * N_TTL * N_PRIO
    assert (N_PLACE, N_TTL, N_PRIO) == (3, 5, 3)
    assert TTL_BUCKETS_S == (5, 30, 120, 600, 3600)


def test_round_trip_all_digit_triples():
    seen = set()
    for p, t, e in itertools.product(range(3), range(5), range(3)):
        a = A.encode_action(p, t, e)
        assert 0 <= a < 45
        assert tuple(A.decode_action(a)) == (p, t, e)
        seen.add(a)
    assert seen == set(range(45))          # bijection: every id hit exactly once


def test_round_trip_all_action_ids():
    for a in range(45):
        p, t, e = A.decode_action(a)
        assert A.encode_action(p, t, e) == a


def test_stride_order_matches_spec():
    """a = p*15 + t*3 + e: placement slowest, priority fastest (C-3 guard)."""
    assert A.encode_action(0, 0, 0) == 0
    assert A.encode_action(0, 0, 1) == 1           # priority is the fastest digit
    assert A.encode_action(0, 1, 0) == 3           # then ttl
    assert A.encode_action(1, 0, 0) == 15          # placement is the slowest digit
    assert A.encode_action(2, 4, 2) == 44
    # the prototype's (wrong) order would give ttl*6 + prio*2 + tier -> not equal here
    assert A.encode_action(0, 1, 0) != 6


def test_decode_semantics():
    a = A.decode_action(A.encode_action(A.PLACE_BOTH, 4, A.PRIO_HIGH))
    assert a.ttl_s == 3600 and a.placement_name == "both" and a.priority_name == "high"
    assert a.writes_l1 and a.writes_l2
    loc = A.decode_action(A.encode_action(A.PLACE_LOCAL, 0, A.PRIO_LOW))
    assert loc.writes_l1 and not loc.writes_l2          # local must NOT write L2 (C-2)
    red = A.decode_action(A.encode_action(A.PLACE_REDIS, 2, A.PRIO_NORMAL))
    assert red.writes_l2 and not red.writes_l1 and red.ttl_s == 120


@pytest.mark.parametrize("args", [(-1, 0, 0), (3, 0, 0), (0, 5, 0), (0, -1, 0), (0, 0, 3), (0, 0, -1)])
def test_encode_rejects_out_of_range(args):
    with pytest.raises(ValueError):
        A.encode_action(*args)


@pytest.mark.parametrize("a", [-1, 45, 100])
def test_decode_rejects_out_of_range(a):
    with pytest.raises(ValueError):
        A.decode_action(a)


def test_types_rejected_or_accepted():
    with pytest.raises(TypeError):
        A.decode_action(1.0)
    with pytest.raises(TypeError):
        A.decode_action(True)
    assert A.decode_action(np.int64(17)) == A.decode_action(17)   # numpy ints from argmax


def test_lookup_tables_agree_with_scalar_codec():
    for a in range(45):
        d = A.decode_action(a)
        assert A.PLACEMENT_OF[a] == d.placement
        assert A.TTL_IDX_OF[a] == d.ttl_idx
        assert A.PRIORITY_OF[a] == d.priority
        assert A.TTL_S_OF[a] == d.ttl_s


def test_actions_where_partitions_space():
    assert len(A.actions_where()) == 45
    assert len(A.actions_where(placement=1)) == 15
    assert len(A.actions_where(ttl_idx=3)) == 9
    assert len(A.actions_where(priority=2)) == 15
    one = A.actions_where(placement=2, ttl_idx=4, priority=0)
    assert list(one) == [A.encode_action(2, 4, 0)]
    # fixing every dimension but one partitions into its cells
    cells = [set(A.actions_where(ttl_idx=t)) for t in range(5)]
    assert set().union(*cells) == set(range(45))
    assert sum(len(c) for c in cells) == 45


def test_nearest_ttl_idx_snaps_in_log_space():
    assert A.nearest_ttl_idx(1) == 0
    assert A.nearest_ttl_idx(5) == 0
    assert A.nearest_ttl_idx(14) == 1        # geometric mean of 5 and 30 is ~12.2
    assert A.nearest_ttl_idx(10) == 0
    assert A.nearest_ttl_idx(10_000) == 4
    assert [A.nearest_ttl_idx(b) for b in TTL_BUCKETS_S] == [0, 1, 2, 3, 4]
