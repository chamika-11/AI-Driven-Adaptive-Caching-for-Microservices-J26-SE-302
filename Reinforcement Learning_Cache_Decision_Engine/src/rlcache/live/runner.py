"""Paced, instrumented replay of policies in the simulator for the live dashboard.

Every policy runs in its own thread over the SAME trace slice; each thread paces itself to the trace's own timestamps
(``speed`` x real time), so the policies stay in step.  Metrics are published every ``publish_every_s`` of wall time.
"""
from __future__ import annotations

import collections
import dataclasses
import math
import threading
import time
from types import SimpleNamespace

import numpy as np

from ..actions import ACTION_TABLE
from ..config import N_ACTIONS, PLACEMENTS, PRIORITY_LEVELS, TTL_BUCKETS_S
from ..evaluation import W_HIT, W_LAT, W_STALE, EvalContext
from ..features import Normalizer
from ..features_spec import FEATURE_NAMES
from ..sim.engine import Simulator
from .metrics import MetricStore


class _Stop(Exception):
    pass


# ---- policy wrappers -------------------------------------------------------------------------------
class CountingPolicy:
    """Wraps any policy: counts every chosen action by (placement, ttl, priority) and delegates the rest."""

    def __init__(self, inner, store: MetricStore, name: str):
        self.inner, self.store, self.name = inner, store, name
        self.counts: dict[int, int] = {}

    def __getattr__(self, item):                       # on_close / on_decision / on_request of the inner policy
        if item in ("inner", "store", "name", "counts"):
            raise AttributeError(item)
        return getattr(self.inner, item)

    def decide(self, ctx) -> int:
        a = int(self.inner.decide(ctx))
        self._record(a)
        return a

    def _record(self, a: int) -> None:
        self.counts[a] = self.counts.get(a, 0) + 1
        x = ACTION_TABLE[a]
        self.store.set_counter("rlcache_action_total", self.counts[a], policy=self.name, placement=PLACEMENTS[x.placement],
                               ttl=str(TTL_BUCKETS_S[x.ttl_idx]), priority=PRIORITY_LEVELS[x.priority])


class AgentPolicy(CountingPolicy):
    """The learned model: runs the network itself so the Q-values and the 19 inputs can be shown."""

    RECENT = 10

    def __init__(self, inner, store, name):
        super().__init__(inner, store, name)
        self.recent: collections.deque = collections.deque(maxlen=self.RECENT)
        self.t0 = 0.0
        self.n_dec = 0
        self.batch = 0

    def publish_recent(self) -> None:
        """The last decisions as a table: one series per decision, value = batch number (a query keeps the current batch)."""
        self.batch += 1
        items = []
        for d in list(self.recent):
            items.append(({"seq": d["seq"], "sim_time": d["t"], "key": d["key"], "size_bytes": d["size"], "placement": d["placement"],
                           "ttl_s": d["ttl"], "priority": d["priority"], "choice": f'{d["placement"]} / {d["ttl"]} s / {d["priority"]}',
                           "q_score": f'{d["q"]:.3f}', "confidence": f'{d["conf"]:.2f}', "batch": self.batch}, self.batch))
        self.store.replace("rlcache_recent_decision", items, policy=self.name)
        self.store.set("rlcache_recent_batch", self.batch, policy=self.name)

    def decide(self, ctx) -> int:
        g = self.inner
        obs = g.tracker.observe(ctx, update_norm=False)
        q = g.net.q_values(obs)
        a = int(np.argmax(q))
        g.action_hist[a] += 1
        self._record(a)
        s, n = self.store, self.name
        x = ACTION_TABLE[a]
        self.n_dec += 1
        t = ctx.ts - self.t0
        zc = np.exp((q - q.max()) / max(float(q.std()), 1e-6))
        self.recent.append({"seq": self.n_dec, "t": f"{int(t // 60):d}:{int(t % 60):02d}", "key": ctx.key, "size": int(ctx.size),
                            "placement": PLACEMENTS[x.placement], "ttl": TTL_BUCKETS_S[x.ttl_idx], "priority": PRIORITY_LEVELS[x.priority],
                            "q": float(q[a]), "conf": float(zc.max() / zc.sum())})
        s.set("rlcache_agent_q_max", float(q[a]), policy=n)
        s.set("rlcache_agent_q_spread", float(q.max() - q.min()), policy=n)
        z = np.exp((q - q.max()) / max(float(q.std()), 1e-6))
        p = z / z.sum()
        s.set("rlcache_agent_choice_confidence", float(p.max()), policy=n)
        s.set("rlcache_agent_q_entropy_norm", float(-(p * np.log(p + 1e-12)).sum() / math.log(N_ACTIONS)), policy=n)
        for i, fname in enumerate(FEATURE_NAMES):
            s.set("rlcache_agent_feature", float(obs[i]), policy=n, feature=fname)
        for dim, labels, idx in (("placement", PLACEMENTS, lambda x: x.placement),
                                 ("ttl", [str(t) for t in TTL_BUCKETS_S], lambda x: x.ttl_idx),
                                 ("priority", PRIORITY_LEVELS, lambda x: x.priority)):
            best: dict[int, float] = {}
            for ai in range(N_ACTIONS):
                k = idx(ACTION_TABLE[ai])
                best[k] = max(best.get(k, -1e18), float(q[ai]))
            for k, v in best.items():
                s.set("rlcache_agent_q_group_max", v, policy=n, dimension=dim, choice=labels[k])
        return a


def load_agent(ckpt_path: str, ctx: EvalContext):
    """Rebuild a greedy numpy policy factory from a saved checkpoint (weights + frozen normaliser)."""
    from ..agents import dqn_train as T
    w, norm_state, meta = T.load_checkpoint(ckpt_path)
    norm = Normalizer(ctx.cfg.features)
    norm.load_state_dict(norm_state)
    res = SimpleNamespace(learner=SimpleNamespace(export_weights=lambda: w), norm=norm,
                          diag={"dueling": bool(meta.get("dueling", True))})
    return (lambda: T.GreedyDQNPolicy(res, ctx)), meta


# ---- the paced run ---------------------------------------------------------------------------------
class _Observer:
    def __init__(self, runner: "LiveRunner", inner):
        self.r, self.inner = runner, inner

    def on_request(self, i, t, k, is_write, hit) -> None:
        if self.inner is not None:
            self.inner.on_request(i, t, k, is_write, hit)
        if (i & 127) == 0:
            self.r.tick(i, t)


class LiveRunner(threading.Thread):
    def __init__(self, name: str, ctx: EvalContext, make_policy, store: MetricStore, *, speed: float = 60.0,
                 eviction: str = "sampled_lru", loop: bool = False, agent: bool = False, start: int | None = None,
                 end: int | None = None, publish_every_s: float = 0.5, window_snaps: int = 20,
                 stop: threading.Event | None = None):
        super().__init__(daemon=True, name=f"live-{name}")
        self.n, self.ctx, self.make_policy, self.store = name, ctx, make_policy, store
        self.speed, self.eviction, self.loop, self.agent = float(speed), eviction, loop, agent
        a, b, _ = ctx.slice_for("test")
        self.a, self.b = (a if start is None else start), (b if end is None else end)
        self.publish_every_s, self.window_snaps = publish_every_s, window_snaps
        self.stop_event = stop or threading.Event()
        self.sim: Simulator | None = None
        self.runs = 0
        self.done = False
        self.error: Exception | None = None

    # -- pacing + publishing -------------------------------------------------------------------------
    def tick(self, i: int, t: float) -> None:
        if self.stop_event.is_set():
            raise _Stop
        target = (t - self._t0) / self.speed
        while True:
            lag = target - (time.perf_counter() - self._w0)
            if lag <= 0:
                break
            time.sleep(min(lag, 0.2))
            if self.stop_event.is_set():
                raise _Stop
        now = time.perf_counter()
        if now - self._last_pub >= self.publish_every_s:
            self._last_pub = now
            self.publish(i, t)

    def publish(self, i: int, t: float) -> None:
        m, s, n = self.sim.metrics, self.store, self.n
        snap = (m.n_reads, m.n_hit, m.n_stale, m.lat_score_hits + m.lat_score_miss, m.stale_cost)
        self._snaps.append(snap)
        old = self._snaps[max(0, len(self._snaps) - 1 - self.window_snaps)]
        dr, dh, ds, dl, dc = (snap[k] - old[k] for k in range(5))
        s.set("rlcache_sim_time_seconds", t - self._t0, policy=n)
        s.set("rlcache_progress_fraction", (i - self.a) / max(self.b - self.a, 1), policy=n)
        s.set_counter("rlcache_reads_total", m.n_reads, policy=n)
        s.set_counter("rlcache_hits_fresh_total", m.n_fresh, policy=n)
        s.set_counter("rlcache_hits_stale_total", m.n_stale, policy=n)
        s.set_counter("rlcache_misses_total", m.n_miss, policy=n)
        s.set_counter("rlcache_decisions_total", m.n_decisions, policy=n)
        s.set_counter("rlcache_backend_fetches_total", m.backend_fetches, policy=n)
        s.set_counter("rlcache_evictions_total", m.cap_evictions, policy=n)
        s.set_counter("rlcache_expirations_total", m.ttl_expirations, policy=n)
        if dr > 0:
            s.set("rlcache_window_hit_ratio", dh / dr, policy=n)
            s.set("rlcache_window_stale_rate", ds / dr, policy=n)
            s.set("rlcache_window_utility", (W_HIT * dh + W_LAT * dl - W_STALE * dc) / dr, policy=n)
        if m.n_reads:
            s.set("rlcache_cum_hit_ratio", m.n_hit / m.n_reads, policy=n)
            s.set("rlcache_cum_stale_rate", m.n_stale / m.n_reads, policy=n)
            s.set("rlcache_cum_utility",
                  (W_HIT * m.n_hit + W_LAT * (m.lat_score_hits + m.lat_score_miss) - W_STALE * m.stale_cost) / m.n_reads, policy=n)
        if self.agent and hasattr(self._pol, "publish_recent"):
            self._pol.publish_recent()
        u1, u2 = self.sim.tier_utilisation()
        s.set("rlcache_tier_utilisation", u1, policy=n, tier="local_L1")
        s.set("rlcache_tier_utilisation", u2, policy=n, tier="redis_L2")

    # -- thread body ---------------------------------------------------------------------------------
    def run(self) -> None:
        try:
            while not self.stop_event.is_set():
                self._one_pass()
                self.runs += 1
                self.store.set("rlcache_replay_runs", self.runs, policy=self.n)
                if not self.loop:
                    break
        except _Stop:
            pass
        except Exception as e:                           # noqa: BLE001
            self.error = e
        self.done = True

    def _one_pass(self) -> None:
        ctx = self.ctx
        cfg = ctx.cfg
        if self.eviction != cfg.cache.base_eviction:
            cfg = dataclasses.replace(cfg, cache=dataclasses.replace(cfg.cache, base_eviction=self.eviction))
        raw = self.make_policy()
        pol = AgentPolicy(raw, self.store, self.n) if self.agent else CountingPolicy(raw, self.store, self.n)
        self._pol = pol
        if self.agent:
            pol.t0 = float(ctx.trace.ts[self.a])
        self._snaps = [(0, 0, 0, 0.0, 0.0)]
        self._t0 = float(ctx.trace.ts[self.a])
        self._w0 = time.perf_counter()
        self._last_pub = 0.0
        sim = Simulator(ctx.trace, cfg, pol, l1_capacity_bytes=ctx.l1_bytes, l2_capacity_bytes=ctx.l2_bytes, seed=ctx.seed,
                        keep_closed=False, record_latencies=False,
                        observer=_Observer(self, raw if hasattr(raw, "on_request") else None))
        self.sim = sim
        sim.run(self.a, self.b, self.a)                 # measure from the first request: the cold start is visible
        self.publish(self.b - 1, float(ctx.trace.ts[self.b - 1]))
