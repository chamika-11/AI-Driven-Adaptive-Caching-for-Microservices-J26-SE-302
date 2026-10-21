"""19-feature state builder and frozen normaliser (M5; R-F1..R-F20, R-P7, R-P8).

All features are functions of (history of requests with index < i, the static attributes of
request i's key, the live simulator state at t_i, the frozen predictor tables) -- see the
timestamp convention in :mod:`rlcache.features_spec`.  The tracker is fed by the simulator's
observer hook AFTER each request has been processed, and queried at a decision point BEFORE the
decision request is recorded, so request ``i`` is never inside its own windows.

Memory is bounded (R-S16): per-key arrays are O(n_keys); windows are fixed-size rings.

Definitions fixed here (each one is this project's own choice, A-9):

* ``log_recency_1`` = log1p(t_i - t_last) / log1p(recency_max);  ``log_recency_2`` is the
  inter-request gap BEFORE the last request, log1p(t_last - t_prev) / log1p(recency_max).
  Never-seen -> sentinel 1.0 (R-F2).
* ``count_{10,100,1000}``: occurrences of the key among the last m requests (reads AND writes),
  divided by m.
* ``edc``: exponentially decayed access counter, half-life ``edc_half_life_s``, over a running max.
* ``hit_ratio``: hits / reads over the last 1000 READS (hit ratio only, INV-1).
* ``request_rate``: requests/s over the last 10 completed seconds; ``rate_cov_10s``: CoV of the
  10 one-second bins; ``rate_cov_300s``: CoV of the 30 ten-second sums over the last 300 s.
* ``top10_share``: share of the last 1000 requests that went to the 10 most requested keys.
* ``invalidation_rate``: writes/s over the last 300 completed seconds.
* ``backend_load``: open backend fetch windows at t_i / ``max_inflight``.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from .config import FeatureConfig, TTL_BUCKETS_S
from .features_spec import FEATURE_INDEX, FEATURE_NAMES
from .predictor.standin import PredictorTables

WIN_S = 300                # longest rate window (completed seconds)
N_BINS = WIN_S + 1         # +1 slot so the in-progress second never aliases sec - 300
_LOG_TTL_MAX = math.log1p(max(TTL_BUCKETS_S))

# indices
_I = FEATURE_INDEX
_ZSCORE_FEATURES = ("backend_latency", "request_rate", "invalidation_rate")   # R-F20 (unbounded)
_RUNMAX_FEATURES = ("edc", "size")


class _EmaZ:
    """Running mean/variance: exact Welford for the first ``n0`` samples, then EMA (alpha)."""

    def __init__(self, alpha: float, n0: int = 200):
        self.alpha, self.n0 = alpha, n0
        self.n, self.mean, self.m2, self.var = 0, 0.0, 0.0, 1.0

    def update(self, x: float) -> None:
        self.n += 1
        if self.n <= self.n0:
            d = x - self.mean
            self.mean += d / self.n
            self.m2 += d * (x - self.mean)
            self.var = self.m2 / max(self.n - 1, 1) if self.n > 1 else 1.0
        else:
            d = x - self.mean
            self.mean += self.alpha * d
            self.var = (1 - self.alpha) * (self.var + self.alpha * d * d)

    def z(self, x: float, clip: float) -> float:
        if self.n < 2:
            return 0.0
        sd = math.sqrt(max(self.var, 1e-12))
        return max(-clip, min(clip, (x - self.mean) / sd))

    def to_dict(self) -> dict:
        return {"n": self.n, "mean": self.mean, "m2": self.m2, "var": self.var}

    def load(self, d: dict) -> None:
        self.n, self.mean, self.m2, self.var = int(d["n"]), d["mean"], d["m2"], d["var"]


class Normalizer:
    """Raw physical features -> network input in [0, 1] (bounded features) or [-1, 1] (z-scored).

    Statistics are learned only while ``frozen`` is False and ``update=True`` (training split;
    R-P7).  ``state_dict()`` goes into the checkpoint so train/serve cannot silently diverge.
    """

    def __init__(self, cfg: FeatureConfig | None = None):
        self.cfg = cfg or FeatureConfig()
        self.frozen = False
        self.size_max = float(self.cfg.size_max_init)
        self.edc_max = 1.0
        self.z = {n: _EmaZ(self.cfg.norm_ema_alpha) for n in _ZSCORE_FEATURES}
        self._den_rec = math.log1p(self.cfg.recency_max_s)

    def freeze(self) -> None:
        self.frozen = True

    def state_dict(self) -> dict[str, Any]:
        return {"frozen": self.frozen, "size_max": self.size_max, "edc_max": self.edc_max,
                "z": {k: v.to_dict() for k, v in self.z.items()}}

    def load_state_dict(self, d: dict[str, Any]) -> None:
        self.frozen = bool(d["frozen"])
        self.size_max, self.edc_max = float(d["size_max"]), float(d["edc_max"])
        for k, v in d["z"].items():
            self.z[k].load(v)

    def transform(self, raw: np.ndarray, update: bool = False) -> np.ndarray:
        """``raw`` is the 19-vector of physical values (see FeatureTracker.raw)."""
        c = self.cfg
        upd = update and not self.frozen
        out = np.empty(19, dtype=np.float32)
        # recency gaps: raw is seconds, negative = never seen -> sentinel 1.0
        for name in ("log_recency_1", "log_recency_2"):
            v = raw[_I[name]]
            out[_I[name]] = 1.0 if v < 0 else min(1.0, math.log1p(v) / self._den_rec)
        out[_I["count_10"]] = min(1.0, raw[_I["count_10"]] / c.win_short)
        out[_I["count_100"]] = min(1.0, raw[_I["count_100"]] / c.win_mid)
        out[_I["count_1000"]] = min(1.0, raw[_I["count_1000"]] / c.win_long)
        # running-max log features
        if upd:
            self.edc_max = max(self.edc_max, float(raw[_I["edc"]]))
            self.size_max = max(self.size_max, float(raw[_I["size"]]))
        out[_I["edc"]] = min(1.0, raw[_I["edc"]] / self.edc_max)
        out[_I["size"]] = min(1.0, math.log1p(raw[_I["size"]]) / math.log1p(self.size_max))
        # z-scored unbounded features, on a log1p scale
        for name in _ZSCORE_FEATURES:
            x = math.log1p(max(float(raw[_I[name]]), 0.0))
            out[_I[name]] = self.z[name].z(x, c.norm_clip) / c.norm_clip
            if upd:
                self.z[name].update(x)
        out[_I["predicted_ttl"]] = min(1.0, math.log1p(raw[_I["predicted_ttl"]]) / _LOG_TTL_MAX)
        for name in ("volatility", "utilisation", "hit_ratio", "top10_share", "hot_key_flag",
                     "backend_load"):
            out[_I[name]] = min(1.0, max(0.0, raw[_I[name]]))
        out[_I["rate_cov_10s"]] = min(1.0, max(0.0, raw[_I["rate_cov_10s"]]))
        out[_I["rate_cov_300s"]] = min(1.0, max(0.0, raw[_I["rate_cov_300s"]]))
        return out


class FeatureTracker:
    """Causal, bounded history -> physical feature vector; also the simulator's observer."""

    def __init__(self, n_keys: int, cfg: FeatureConfig | None = None,
                 predictor: PredictorTables | None = None,
                 normalizer: Normalizer | None = None):
        self.cfg = cfg or FeatureConfig()
        self.n_keys = n_keys
        self.pred = predictor or PredictorTables.absent(n_keys)
        if self.pred.n_keys < n_keys:
            raise ValueError("predictor tables smaller than the key space")
        self.norm = normalizer or Normalizer(self.cfg)
        self._vol = self.pred.volatility.tolist()
        self._ttl = self.pred.predicted_ttl.tolist()
        self._hot = self.pred.hot_key.tolist()
        self._t1 = [-1.0] * n_keys                 # last access time
        self._t2 = [-1.0] * n_keys                 # access before that
        self._edc_v = [0.0] * n_keys
        self._edc_t = [-1.0] * n_keys
        self._ln2_hl = math.log(2.0) / self.cfg.edc_half_life_s
        W = self.cfg.win_long
        self._W = W
        self._ring = [-1] * W
        self._head = 0
        self._n = 0
        self._counts: dict[int, int] = {}
        self._hit_ring = [0] * W
        self._hit_head = 0
        self._hit_n = 0
        self._hit_sum = 0
        self._req_bins = [0] * N_BINS
        self._wr_bins = [0] * N_BINS
        self._cur_sec: int | None = None
        self._first_sec = 0
        self.n_observed = 0

    # ---- feed (simulator observer) -------------------------------------------------------------
    def _roll(self, sec: int) -> None:
        if self._cur_sec is None:
            self._cur_sec = self._first_sec = sec
            return
        if sec > self._cur_sec:
            for j in range(1, min(sec - self._cur_sec, N_BINS) + 1):
                b = (self._cur_sec + j) % N_BINS
                self._req_bins[b] = 0
                self._wr_bins[b] = 0
            self._cur_sec = sec

    def on_request(self, i: int, t: float, k: int, is_write: bool, hit) -> None:
        sec = int(t)
        self._roll(sec)
        b = sec % N_BINS
        self._req_bins[b] += 1
        if is_write:
            self._wr_bins[b] += 1
        self._t2[k] = self._t1[k]
        self._t1[k] = t
        et = self._edc_t[k]
        self._edc_v[k] = (self._edc_v[k] * math.exp(-(t - et) * self._ln2_hl) if et >= 0 else 0.0) + 1.0
        self._edc_t[k] = t
        W = self._W
        if self._n == W:
            old = self._ring[self._head]
            c = self._counts[old] - 1
            if c:
                self._counts[old] = c
            else:
                del self._counts[old]
        else:
            self._n += 1
        self._ring[self._head] = k
        self._counts[k] = self._counts.get(k, 0) + 1
        self._head = (self._head + 1) % W
        if not is_write:
            h = 1 if hit else 0
            if self._hit_n == W:
                self._hit_sum -= self._hit_ring[self._hit_head]
            else:
                self._hit_n += 1
            self._hit_ring[self._hit_head] = h
            self._hit_sum += h
            self._hit_head = (self._hit_head + 1) % W
        self.n_observed += 1

    # ---- query -------------------------------------------------------------------------------------
    def _count_last(self, k: int, m: int) -> int:
        m = min(m, self._n)
        W, head, ring = self._W, self._head, self._ring
        return sum(1 for j in range(1, m + 1) if ring[(head - j) % W] == k)

    def _rate_stats(self, sec: int) -> tuple[float, float, float, float]:
        """(rate over last 10 s, cov10, cov300, write rate over last 300 s) from COMPLETED bins."""
        avail = max(0, min(WIN_S, sec - self._first_sec))
        if avail == 0:
            return 0.0, 0.0, 0.0, 0.0
        rb, wb = self._req_bins, self._wr_bins
        a10 = min(10, avail)
        v10 = [rb[(sec - j) % N_BINS] for j in range(1, a10 + 1)]
        rate = sum(v10) / a10
        cov10 = 0.0
        if a10 >= 2 and rate > 0:
            cov10 = float(np.std(v10)) / rate
        g = avail // 10
        cov300 = 0.0
        if g >= 2:
            sums = [sum(rb[(sec - 10 * q - j) % N_BINS] for j in range(1, 11)) for q in range(g)]
            m = sum(sums) / g
            if m > 0:
                cov300 = float(np.std(sums)) / m
        wr = sum(wb[(sec - j) % N_BINS] for j in range(1, avail + 1)) / avail
        return rate, cov10, cov300, wr

    def raw(self, ctx) -> np.ndarray:
        """Physical (unnormalised) 19-vector at the decision point described by ``ctx``."""
        k, t = ctx.key, ctx.ts
        sim = ctx.sim
        sec = int(t)
        self._roll(sec)
        c = self.cfg
        r = np.zeros(19, dtype=np.float64)
        t1, t2 = self._t1[k], self._t2[k]
        r[_I["log_recency_1"]] = (t - t1) if t1 >= 0 else -1.0
        r[_I["log_recency_2"]] = (t1 - t2) if t2 >= 0 else -1.0
        r[_I["count_10"]] = self._count_last(k, c.win_short)
        r[_I["count_100"]] = self._count_last(k, c.win_mid)
        r[_I["count_1000"]] = self._counts.get(k, 0)
        et = self._edc_t[k]
        r[_I["edc"]] = self._edc_v[k] * math.exp(-(t - et) * self._ln2_hl) if et >= 0 else 0.0
        r[_I["size"]] = ctx.size
        r[_I["backend_latency"]] = sim.key_backend_s[k] * 1e3          # ms
        r[_I["predicted_ttl"]] = self._ttl[k]
        r[_I["volatility"]] = self._vol[k]
        r[_I["utilisation"]] = sim.utilisation()
        r[_I["hit_ratio"]] = (self._hit_sum / self._hit_n) if self._hit_n else 0.0
        rate, cov10, cov300, wr = self._rate_stats(sec)
        r[_I["request_rate"]] = rate
        r[_I["rate_cov_10s"]] = cov10
        r[_I["rate_cov_300s"]] = cov300
        if self._n:
            top = sorted(self._counts.values(), reverse=True)[:c.top_k_share]
            r[_I["top10_share"]] = sum(top) / self._n
        r[_I["invalidation_rate"]] = wr
        r[_I["backend_load"]] = min(1.0, sim.inflight(t) / c.max_inflight)
        r[_I["hot_key_flag"]] = self._hot[k]
        return r

    def observe(self, ctx, update_norm: bool = False) -> np.ndarray:
        return self.norm.transform(self.raw(ctx), update=update_norm)


__all__ = ["FeatureTracker", "Normalizer", "FEATURE_NAMES"]
