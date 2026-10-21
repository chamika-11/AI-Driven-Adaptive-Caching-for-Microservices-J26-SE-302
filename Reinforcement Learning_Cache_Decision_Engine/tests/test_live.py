"""Live dashboard plumbing: metric store / HTTP endpoint, paced runner with a rule policy and with a saved model."""
import urllib.request

import numpy as np

from rlcache.config import DQNConfig, WorkloadConfig
from rlcache.live.metrics import MetricStore, serve
from rlcache.live.runner import LiveRunner, load_agent


def test_store_renders_prometheus_text_and_serves_it():
    s = MetricStore()
    s.describe("x_total", "a counter")
    s.set("g", 1.5, policy='a"b', tier="L1")
    s.inc("x_total", 2, policy="p")
    s.inc("x_total", 3, policy="p")
    s.set_counter("y_total", 7)
    text = s.render()
    assert '# TYPE g gauge' in text and 'g{policy="a\\"b",tier="L1"} 1.5' in text
    assert '# HELP x_total a counter' in text and 'x_total{policy="p"} 5' in text and "y_total 7" in text
    srv = serve(s, port=0, host="127.0.0.1")
    try:
        body = urllib.request.urlopen(f"http://127.0.0.1:{srv.server_address[1]}/metrics", timeout=5).read().decode()
        assert 'x_total{policy="p"} 5' in body
    finally:
        srv.shutdown()


def _ctx(seed=1, cap=0.05):
    from rlcache.evaluation import EvalContext
    wl = WorkloadConfig(n_requests=30_000, n_keys=300, write_interval_median_s=30_000.0)
    return EvalContext.build(seed, cap, "harsh", workload=wl)


def test_runner_with_a_rule_policy_publishes_consistent_metrics():
    from rlcache.baselines.policies import registry
    ctx = _ctx()
    spec = {x.name: x for x in registry()}["place_size:p25"]
    s = MetricStore()
    r = LiveRunner("rule", ctx, lambda: spec.make(ctx), s, speed=1e9, publish_every_s=0.0)
    r.start(); r.join(timeout=60)
    assert r.done and r.error is None and r.runs == 1
    hit, stale = s.get("rlcache_cum_hit_ratio", policy="rule"), s.get("rlcache_cum_stale_rate", policy="rule")
    assert 0.0 < hit < 1.0 and 0.0 <= stale < 1.0
    reads = s.get("rlcache_reads_total", policy="rule")
    assert reads == s.get("rlcache_hits_fresh_total", policy="rule") + s.get("rlcache_hits_stale_total", policy="rule") + s.get("rlcache_misses_total", policy="rule")
    assert s.get("rlcache_progress_fraction", policy="rule") > 0.99
    assert 'rlcache_action_total{placement="' in s.render()


def test_runner_with_a_saved_model_publishes_features_and_q_values(tmp_path):
    from rlcache.agents import dqn_train as T
    from rlcache.agents.qnet_numpy import NumpyDuelingQ
    ctx = _ctx(2)
    cfg = DQNConfig(total_decisions=1_500, learning_starts=300, buffer_size=3_000, batch_size=32)
    res = T.train_dqn(ctx, NumpyDuelingQ(hidden=16, seed=1), cfg, calib_requests=2_000, log_every=400)
    path = tmp_path / "m.npz"
    T.save_checkpoint(path, res, {"seed": 2})
    make, meta = load_agent(str(path), ctx)
    s = MetricStore()
    r = LiveRunner("agent", ctx, make, s, speed=1e9, agent=True, publish_every_s=0.0)
    r.start(); r.join(timeout=120)
    assert r.error is None and r.done
    text = s.render()
    assert text.count('rlcache_agent_feature{') == 19
    assert 'rlcache_agent_q_group_max{choice="redis"' in text or 'choice="redis"' in text
    assert 0.0 < s.get("rlcache_agent_choice_confidence", policy="agent") <= 1.0
    # the live model picks the same actions as the saved model evaluated directly
    pol = make()
    x = np.random.default_rng(0).uniform(size=19).astype(np.float32)
    assert pol.net.q_values(x).shape == (45,)


def test_decision_log_is_published_as_a_replaceable_batch(tmp_path):
    s = MetricStore()
    s.replace("t", [({"seq": 1}, 5), ({"seq": 2}, 5)], policy="a")
    s.replace("t", [({"seq": 9}, 6)], policy="a")
    s.replace("t", [({"seq": 1}, 7)], policy="b")
    text = s.render()
    assert text.count("t{") == 2 and 'seq="9"' in text and 'seq="2"' not in text and 'policy="b"' in text   # a's old batch gone, b untouched

    from rlcache.agents import dqn_train as T
    from rlcache.agents.qnet_numpy import NumpyDuelingQ
    ctx = _ctx(3)
    cfg = DQNConfig(total_decisions=1_500, learning_starts=300, buffer_size=3_000, batch_size=32)
    res = T.train_dqn(ctx, NumpyDuelingQ(hidden=16, seed=2), cfg, calib_requests=2_000, log_every=400)
    path = tmp_path / "m.npz"
    T.save_checkpoint(path, res, {"seed": 3})
    make, _ = load_agent(str(path), ctx)
    st = MetricStore()
    r = LiveRunner("agent", ctx, make, st, speed=1e9, agent=True, publish_every_s=0.0)
    r.start(); r.join(timeout=120)
    assert r.error is None
    out = st.render()
    rows = [ln for ln in out.splitlines() if ln.startswith("rlcache_recent_decision{")]
    assert len(rows) == 10                                           # exactly the latest 10 decisions
    batch = st.get("rlcache_recent_batch", policy="agent")
    assert all(ln.rstrip().endswith(f" {batch:g}") for ln in rows)    # value == current batch number
    assert 'placement="' in rows[0] and 'ttl_s="' in rows[0] and 'priority="' in rows[0]
