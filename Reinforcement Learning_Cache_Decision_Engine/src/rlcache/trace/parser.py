"""Streaming parser for the Twitter Twemcache plain-text trace (R-D2, R-D3, R-D4, R-D5).

Schema (one request per row, comma separated, no header):

    timestamp, anonymized key, key size, value size, client id, operation, TTL

* Never loads a whole shard: lines are consumed in blocks and the read stops as soon as the
  timestamp passes ``t_end`` (traces are time ordered), so slicing a time window of a 1e9-row
  zstd shard costs only the window.
* ``.zst`` files are decompressed as a stream (``zstandard``); anything else is read as text.
* Sampling is by contiguous time window or by key-space hash (``key_hash_pct``) -- never uniform
  row sampling (R-D5).  Key-space sampling records the sampled fraction in ``meta`` so the
  simulator's capacity can be scaled by the same factor (:func:`scaled_capacity`).
* The effective object size is forward-filled CAUSALLY: a row whose value size is 0 (e.g. a
  delete or an unknown miss size) inherits the last non-zero size seen for that key *earlier* in
  the stream, never a later one.
"""
from __future__ import annotations

import io
import zlib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import numpy as np

from .record import DEFAULT_OBJECT_SIZE, OP_CODE, OPS, Trace

N_FIELDS = 7
_BLOCK = 200_000


@dataclass
class ParseStats:
    rows_read: int = 0
    rows_kept: int = 0
    rows_bad_fieldcount: int = 0
    rows_bad_value: int = 0
    rows_unknown_op: int = 0
    rows_out_of_order: int = 0
    rows_dropped_by_key_sampling: int = 0
    stopped_early_at_ts: float | None = None

    @property
    def bad_fraction(self) -> float:
        bad = self.rows_bad_fieldcount + self.rows_bad_value + self.rows_unknown_op
        return bad / max(self.rows_read, 1)


def _open_text(path: str | Path) -> io.TextIOBase:
    p = Path(path)
    if p.suffix == ".zst":
        import zstandard
        raw = open(p, "rb")
        reader = zstandard.ZstdDecompressor().stream_reader(raw)
        return io.TextIOWrapper(reader, encoding="utf-8", errors="replace", newline="")
    return open(p, "r", encoding="utf-8", errors="replace", newline="")


def key_hash_bucket(key: str) -> int:
    """Stable key-space hash in [0, 100) (the MD's ``crc32(key) % 100``)."""
    return zlib.crc32(key.encode("utf-8")) % 100


def parse_trace(path: str | Path, *, t_start: float | None = None, t_end: float | None = None,
                max_rows: int | None = None, key_hash_pct: int | None = None,
                max_bad_fraction: float = 0.001, name: str | None = None,
                ) -> tuple[Trace, ParseStats]:
    """Parse a (slice of a) Twitter trace file into a :class:`Trace`.

    ``t_start``/``t_end`` select the half-open time window ``[t_start, t_end)`` in the trace's own
    seconds.  ``max_rows`` bounds rows *kept*.  ``key_hash_pct`` keeps every request of keys with
    ``crc32(key) % 100 < pct`` (spatial sampling).
    """
    if key_hash_pct is not None and not 0 < key_hash_pct <= 100:
        raise ValueError("key_hash_pct must be in (0, 100]")
    st = ParseStats()
    ts_l: list[float] = []; key_l: list[int] = []; size_l: list[int] = []
    cli_l: list[int] = []; op_l: list[int] = []; ttl_l: list[int] = []
    intern: dict[str, int] = {}
    last_size: dict[int, int] = {}
    last_ts = -np.inf
    done = False

    with _open_text(path) as fh:
        while not done:
            block = fh.readlines(_BLOCK * 64)           # ~size hint in bytes, bounded memory
            if not block:
                break
            for line in block:
                st.rows_read += 1
                parts = line.rstrip("\r\n").split(",")
                if len(parts) != N_FIELDS:
                    st.rows_bad_fieldcount += 1
                    continue
                opcode = OP_CODE.get(parts[5])
                if opcode is None:
                    st.rows_unknown_op += 1
                    continue
                try:
                    t = float(parts[0]); ksz = int(parts[2]); vsz = int(parts[3])
                    cli = int(parts[4]); ttl = int(parts[6])
                except ValueError:
                    st.rows_bad_value += 1
                    continue
                if t_end is not None and t >= t_end:
                    st.stopped_early_at_ts = t
                    done = True
                    break
                if t_start is not None and t < t_start:
                    continue
                skey = parts[1]
                if key_hash_pct is not None and key_hash_bucket(skey) >= key_hash_pct:
                    st.rows_dropped_by_key_sampling += 1
                    continue
                kid = intern.get(skey)
                if kid is None:
                    kid = len(intern)
                    intern[skey] = kid
                raw_size = ksz + vsz
                if vsz > 0:
                    size = max(raw_size, 1)
                    last_size[kid] = size
                else:                                   # causal forward fill
                    size = last_size.get(kid, DEFAULT_OBJECT_SIZE)
                if t < last_ts:
                    st.rows_out_of_order += 1
                last_ts = max(last_ts, t)
                ts_l.append(t); key_l.append(kid); size_l.append(size)
                cli_l.append(cli); op_l.append(opcode)
                ttl_l.append(ttl if opcode >= OP_CODE["set"] else 0)
                st.rows_kept += 1
                if max_rows is not None and st.rows_kept >= max_rows:
                    done = True
                    break

    if st.rows_read and st.bad_fraction > max_bad_fraction:
        raise ValueError(
            f"{path}: {st.bad_fraction:.4%} of rows malformed (limit {max_bad_fraction:.4%}); "
            f"fieldcount={st.rows_bad_fieldcount} value={st.rows_bad_value} "
            f"op={st.rows_unknown_op}")

    ts = np.asarray(ts_l, dtype=np.float64)
    if st.rows_out_of_order:                            # stable sort keeps same-ts order
        order = np.argsort(ts, kind="stable")
        ts = ts[order]
        key_l = np.asarray(key_l)[order]; size_l = np.asarray(size_l)[order]
        cli_l = np.asarray(cli_l)[order]; op_l = np.asarray(op_l)[order]
        ttl_l = np.asarray(ttl_l)[order]
    tr = Trace(ts=ts, key=np.asarray(key_l, dtype=np.int64),
               size=np.asarray(size_l, dtype=np.int32), client=np.asarray(cli_l, dtype=np.int32),
               op=np.asarray(op_l, dtype=np.int8), ttl=np.asarray(ttl_l, dtype=np.int32),
               n_keys=max(len(intern), 1), source="twitter_real",
               name=name or Path(path).name,
               meta={"key_sample_frac": (key_hash_pct / 100.0) if key_hash_pct else 1.0,
                     "t_start": t_start, "t_end": t_end, "parse": st})
    if len(tr):
        tr.validate()
    return tr, st


def scaled_capacity(capacity_bytes: float, trace: Trace) -> float:
    """R-D5: capacity must be scaled by the same fraction as key-space sampling."""
    return capacity_bytes * float(trace.meta.get("key_sample_frac", 1.0))


# ---- namespace helpers (R-D3: delimiters are not always ':') ------------------------------
_CANDIDATE_DELIMS = (":", "/", "_", "-", ".", "|")


def infer_namespace_delimiter(sample_keys: list[str], min_support: float = 0.5) -> str | None:
    """Pick the delimiter that splits most keys into a *low-cardinality* prefix.

    A real namespace delimiter yields few distinct prefixes relative to the number of keys; a
    delimiter that merely occurs inside random strings yields almost one prefix per key.
    Returns ``None`` when no candidate qualifies (e.g. fully hashed keys).
    """
    n = len(sample_keys)
    if n == 0:
        return None
    best, best_score = None, 0.0
    for d in _CANDIDATE_DELIMS:
        prefixes = [k.split(d, 1)[0] for k in sample_keys if d in k]
        support = len(prefixes) / n
        if support < min_support:
            continue
        card = len(set(prefixes))
        compression = 1.0 - card / len(prefixes)         # 0 = all unique, ->1 = few prefixes
        score = support * compression
        if compression >= 0.5 and score > best_score:
            best, best_score = d, score
    return best


def key_namespace(key: str, delim: str | None) -> str:
    return key.split(delim, 1)[0] if delim and delim in key else ""


def iter_raw_rows(path: str | Path, limit: int | None = None) -> Iterator[list[str]]:
    """Yield raw split rows (used by tests and the data-profiling script)."""
    with _open_text(path) as fh:
        for i, line in enumerate(fh):
            if limit is not None and i >= limit:
                return
            yield line.rstrip("\r\n").split(",")


def profile_trace(tr: Trace) -> dict:
    """Compact descriptive profile used when recording what a real shard looked like."""
    w = tr.is_write
    writes_per_key = np.bincount(tr.key[w], minlength=tr.n_keys)
    wk = writes_per_key[writes_per_key > 0]
    ttl_w = tr.ttl[w]
    return {
        "rows": len(tr), "span_s": tr.duration_s, "unique_keys": tr.n_unique_keys(),
        "ops": tr.op_counts(), "write_fraction": tr.write_fraction(),
        "keys_written": int((writes_per_key > 0).sum()),
        "writes_per_written_key_median": float(np.median(wk)) if wk.size else 0.0,
        "writes_per_written_key_max": int(wk.max()) if wk.size else 0,
        "write_ttl_top": Counter(ttl_w.tolist()).most_common(5),
        "footprint_bytes": tr.footprint_bytes(),
    }


def forward_fill_ttl_label(tr: Trace) -> np.ndarray:
    """R-D4: the TTL of the most recent EARLIER write to the same key, 0 if none.

    Causal by construction: a row's label depends only on writes with a smaller index, so it can
    be used as a "which TTL did the engineers choose" label without leaking the future.  A write
    row's own label is the previous write's TTL (its own TTL is available as ``tr.ttl``).
    """
    out = np.zeros(len(tr), dtype=np.int32)
    last: dict[int, int] = {}
    keys = tr.key.tolist()
    ttl = tr.ttl.tolist()
    wr = tr.is_write.tolist()
    for i in range(len(keys)):
        k = keys[i]
        out[i] = last.get(k, 0)
        if wr[i] and ttl[i] > 0:
            last[k] = ttl[i]
    return out
