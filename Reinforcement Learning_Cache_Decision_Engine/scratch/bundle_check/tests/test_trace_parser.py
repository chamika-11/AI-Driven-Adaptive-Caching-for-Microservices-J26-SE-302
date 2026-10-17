"""M2 gate (parser): all 11 ops, non-':' namespaces, causal size fill, windows, sampling, zstd,
malformed rows, and a real-shard smoke test (skipped if the download is absent)."""
from pathlib import Path

import numpy as np
import pytest

from rlcache.trace import parser as P
from rlcache.trace.record import DEFAULT_OBJECT_SIZE, OP_CODE, OPS, Trace

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "twitter_mini.csv"
REAL = ROOT / "data" / "raw" / "twitter_samples_2020Mar" / "cluster012"


@pytest.fixture(scope="module")
def mini():
    tr, st = P.parse_trace(FIX)
    return tr, st


def test_fixture_parses_all_rows(mini):
    tr, st = mini
    assert len(tr) == 20 and st.rows_read == 20 and st.rows_kept == 20
    assert st.rows_bad_fieldcount == st.rows_bad_value == st.rows_unknown_op == 0
    assert tr.source == "twitter_real"


def test_all_eleven_operations_recognised(mini):
    tr, _ = mini
    assert len(OPS) == 11
    seen = {OPS[c] for c in np.unique(tr.op)}
    assert seen == set(OPS)


def test_read_write_classification(mini):
    tr, _ = mini
    reads = {OPS[c] for c in np.unique(tr.op[tr.is_read])}
    writes = {OPS[c] for c in np.unique(tr.op[tr.is_write])}
    assert reads == {"get", "gets"}
    assert writes == {"set", "add", "replace", "cas", "append", "prepend", "incr", "decr", "delete"}
    assert tr.is_read.sum() + tr.is_write.sum() == len(tr)


def test_ttl_only_on_writes(mini):
    tr, _ = mini
    assert np.all(tr.ttl[tr.is_read] == 0)
    assert tr.ttl[0] == 0 and tr.ttl[1] == 300          # get -> 0, set -> 300
    assert tr.ttl[tr.op == OP_CODE["add"]][0] == 60


def test_key_interning_is_dense_and_stable(mini):
    tr, _ = mini
    assert tr.n_keys == 8                               # distinct string keys in the fixture
    assert tr.key.min() == 0 and tr.key.max() == tr.n_keys - 1
    assert tr.key[0] == tr.key[1] == tr.key[7]          # user:1001
    assert tr.key[0] != tr.key[2]


def test_size_is_causal_forward_fill(mini):
    tr, _ = mini
    k_cfg = tr.key[5]
    assert tr.size[5] == 8 + 50                         # replace, value size known
    assert tr.size[6] == 8 + 50                         # get with vsz 0 inherits EARLIER size
    assert tr.size[2] == DEFAULT_OBJECT_SIZE            # first-ever sighting, vsz 0 -> default
    assert tr.size[12] == DEFAULT_OBJECT_SIZE           # delete of key whose size was never known
    assert tr.key[6] == k_cfg


def test_causality_of_size_fill():
    """A later size must never back-fill an earlier row."""
    import io, tempfile, os
    rows = "0,k,4,0,1,get,0\n1,k,4,500,1,set,60\n2,k,4,0,1,get,0\n"
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "t.csv"); open(p, "w").write(rows)
        tr, _ = P.parse_trace(p)
    assert tr.size.tolist() == [DEFAULT_OBJECT_SIZE, 504, 504]


def test_time_window_and_early_stop():
    tr, st = P.parse_trace(FIX, t_start=2, t_end=5)
    assert tr.ts.min() >= 2 and tr.ts.max() < 5
    assert len(tr) == 6                                  # rows with ts in {2,2,3,3,4,4}
    assert st.stopped_early_at_ts == 5.0                 # stopped streaming at first ts >= t_end


def test_max_rows():
    tr, st = P.parse_trace(FIX, max_rows=7)
    assert len(tr) == 7 and st.rows_kept == 7


def test_key_hash_sampling_keeps_whole_keys_and_records_fraction(tmp_path):
    rng = np.random.default_rng(0)
    keys = [f"k{i}" for i in range(500)]
    lines = [f"{t},{keys[rng.integers(0, 500)]},4,10,1,get,0" for t in range(4000)]
    p = tmp_path / "t.csv"; p.write_text("\n".join(lines) + "\n")
    full, _ = P.parse_trace(p)
    samp, st = P.parse_trace(p, key_hash_pct=20)
    assert samp.meta["key_sample_frac"] == 0.2
    assert 0.1 < len(samp) / len(full) < 0.3
    assert st.rows_dropped_by_key_sampling == len(full) - len(samp)
    # every request of a retained key is retained (spatial, not row, sampling)
    kept_names = {k for k in keys if P.key_hash_bucket(k) < 20}
    expected = sum(1 for ln in lines if ln.split(",")[1] in kept_names)
    assert len(samp) == expected
    assert P.scaled_capacity(1000.0, samp) == pytest.approx(200.0)   # R-D5 capacity scaling


def test_zstd_stream_matches_plain(tmp_path):
    zstandard = pytest.importorskip("zstandard")
    raw = FIX.read_bytes()
    z = tmp_path / "mini.csv.zst"
    z.write_bytes(zstandard.ZstdCompressor().compress(raw))
    a, _ = P.parse_trace(FIX)
    b, _ = P.parse_trace(z)
    for col in ("ts", "key", "size", "client", "op", "ttl"):
        assert np.array_equal(getattr(a, col), getattr(b, col))


def test_malformed_rows_counted_and_limit_enforced(tmp_path):
    good = [f"{i},k{i},4,10,1,get,0" for i in range(2000)]
    bad = ["1,2,3", "x,k,4,10,1,get,0", "5,k,4,10,1,frobnicate,0"]
    p = tmp_path / "t.csv"; p.write_text("\n".join(good + bad) + "\n")
    tr, st = P.parse_trace(p, max_bad_fraction=0.01)
    assert len(tr) == 2000
    assert (st.rows_bad_fieldcount, st.rows_bad_value, st.rows_unknown_op) == (1, 1, 1)
    p2 = tmp_path / "t2.csv"; p2.write_text("\n".join(["junk"] * 50 + good[:50]) + "\n")
    with pytest.raises(ValueError):
        P.parse_trace(p2)                                # >0.1% malformed


def test_out_of_order_rows_are_sorted_and_counted(tmp_path):
    p = tmp_path / "t.csv"
    p.write_text("5,a,1,1,1,get,0\n3,b,1,1,1,get,0\n4,a,1,1,1,set,10\n")
    tr, st = P.parse_trace(p)
    assert st.rows_out_of_order >= 1
    assert np.all(np.diff(tr.ts) >= 0)


def test_namespace_delimiter_inference_not_always_colon():
    colon = [f"user:{i}" for i in range(100)] + [f"feed:{i}" for i in range(100)]
    slash = [f"tweets/{i}/x" for i in range(100)] + [f"graph/{i}/y" for i in range(100)]
    under = [f"cfg_{i}" for i in range(100)] + [f"ctr_{i}" for i in range(100)]
    hashed = ["SbDacwXjDwKPOgfdaTy0VZWDJYRXeOx4O5+Drbq5Ejf=%d" % i for i in range(200)]
    assert P.infer_namespace_delimiter(colon) == ":"
    assert P.infer_namespace_delimiter(slash) == "/"
    assert P.infer_namespace_delimiter(under) == "_"
    assert P.infer_namespace_delimiter(hashed) is None
    assert P.key_namespace("user:1001", ":") == "user"
    assert P.key_namespace("nodelim", ":") == ""


def test_profile_reports_expected_fields(mini):
    prof = P.profile_trace(mini[0])
    assert prof["rows"] == 20 and prof["unique_keys"] == 8
    assert 0 < prof["write_fraction"] < 1


@pytest.mark.realdata
@pytest.mark.skipif(not REAL.exists(), reason="real Twitter sample not downloaded")
def test_real_cluster012_prefix_schema():
    tr, st = P.parse_trace(REAL, max_rows=50_000)
    assert len(tr) == 50_000 and st.bad_fraction == 0.0
    assert set(tr.op_counts()) <= set(OPS)
    w = tr.is_write
    assert w.sum() > 0 and np.all(tr.ttl[w][tr.op[w] == OP_CODE["set"]] > 0)   # nonzero TTL on set
    assert np.all(tr.ttl[~w] == 0)                                              # zero on reads
    assert tr.n_keys > 1000


def test_ttl_label_forward_fill_is_causal():
    """R-D4: label = TTL of the most recent EARLIER write; never a later one."""
    import os, tempfile
    rows = ("0,a,1,1,1,get,0\n"         # no earlier write -> 0
            "1,a,1,1,1,set,300\n"        # label = previous write's TTL = 0 (own TTL not leaked)
            "2,a,1,1,1,get,0\n"          # 300
            "3,b,1,1,1,get,0\n"          # other key -> 0
            "4,a,1,1,1,set,60\n"
            "5,a,1,1,1,get,0\n")         # 60
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "t.csv"); open(p, "w").write(rows)
        tr, _ = P.parse_trace(p)
    assert P.forward_fill_ttl_label(tr).tolist() == [0, 0, 300, 0, 300, 60]
