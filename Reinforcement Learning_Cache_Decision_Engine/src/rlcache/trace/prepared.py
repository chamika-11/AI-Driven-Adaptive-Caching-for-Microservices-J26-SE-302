"""Save / load a prepared (sampled) real trace as one compressed .npz (Addendum R1)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .record import Trace


def save_prepared(tr: Trace, path: str | Path, extra_meta: dict | None = None) -> None:
    meta = dict(extra_meta or {})
    meta["key_sample_frac"] = float(tr.meta.get("key_sample_frac", 1.0))
    meta["source"] = tr.source
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, ts=tr.ts, key=tr.key, size=tr.size, client=tr.client, op=tr.op, ttl=tr.ttl,
                        n_keys=np.int64(tr.n_keys), name=np.bytes_(tr.name.encode()),
                        meta=np.frombuffer(json.dumps(meta, default=str).encode(), dtype=np.uint8))


def load_prepared(path: str | Path) -> Trace:
    z = np.load(path, allow_pickle=False)
    meta = json.loads(bytes(z["meta"]).decode())
    tr = Trace(ts=z["ts"], key=z["key"], size=z["size"], client=z["client"], op=z["op"], ttl=z["ttl"],
               n_keys=int(z["n_keys"]), source=meta.get("source", "twitter_real"), name=bytes(z["name"]).decode(),
               meta={"key_sample_frac": float(meta.get("key_sample_frac", meta.get("key_sample_pct", 100) / 100.0)), "prepared": meta,
                     "spread_timestamps": True})
    tr.validate()
    return tr
