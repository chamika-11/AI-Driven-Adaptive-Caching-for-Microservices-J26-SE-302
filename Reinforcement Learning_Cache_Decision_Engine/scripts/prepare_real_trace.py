"""Turn a downloaded Twitter trace part into a small sampled .npz the experiments can load (R-D5).

    python scripts/prepare_real_trace.py data/raw/twitter_full/cluster52.000.zst --pct 1 --out data/processed/cluster52_000_k1.npz

Streams the .zst (never loads it whole), keeps every request of keys with crc32(key) % 100 < pct (spatial sampling, the
sampled fraction is recorded and capacities must be scaled by it), spreads same-second timestamps, records the SHA-256 of the
raw file.  The raw download is untrusted input: run this script with `python -I` if you like.
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rlcache.trace.parser import parse_trace, profile_trace  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("path", nargs="+", help="one or more CONSECUTIVE parts, in order")
ap.add_argument("--pct", type=int, default=1)
ap.add_argument("--out", required=True)
ap.add_argument("--max-rows", type=int, default=None)
a = ap.parse_args()
srcs = [Path(x) for x in a.path]
src = srcs[0]
t0 = time.time()
shas = {}
for sp in srcs:
    h = hashlib.sha256()
    with open(sp, "rb") as fh:
        for blk in iter(lambda: fh.read(1 << 24), b""):
            h.update(blk)
    shas[sp.name] = h.hexdigest()
    print("sha256", sp.name, h.hexdigest(), f"({time.time()-t0:.0f}s)", flush=True)
label = srcs[0].stem if len(srcs) == 1 else f"{srcs[0].stem}-{srcs[-1].suffixes[0].strip('.') if srcs[-1].suffixes else ''}"
tr, st = parse_trace(srcs, key_hash_pct=a.pct, max_rows=a.max_rows, name=f"{label}_k{a.pct}")
print("parse", vars(st), f"({time.time()-t0:.0f}s)", flush=True)
tr = tr.with_spread_timestamps()
tr.validate()
meta = {"source_files": [x.name for x in srcs], "source_sha256": shas, "key_sample_pct": a.pct,
        "rows_read": st.rows_read, "rows_kept": st.rows_kept, "profile": profile_trace(tr)}
from rlcache.trace.prepared import save_prepared  # noqa: E402
save_prepared(tr, a.out, meta)
print("saved", a.out, Path(a.out).stat().st_size / 1e6, "MB;", json.dumps(meta["profile"], default=str)[:900])
