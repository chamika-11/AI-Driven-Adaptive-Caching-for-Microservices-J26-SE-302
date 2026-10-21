"""Generate the Grafana dashboard JSON for the live replay (live/grafana/dashboards/rl_cache.json).

    python scripts/make_grafana_dashboard.py
Data source: Prometheus (uid "prom") scraping scripts/live_dashboard.py.  The dashboard depends only on metric names, so it works
unchanged for any trace / model / number of policies.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "live" / "grafana" / "dashboards" / "rl_cache.json"
DS = {"type": "prometheus", "uid": "prom"}
AGENT = "agent (RL model)"
_id = [0]


def _nid():
    _id[0] += 1
    return _id[0]


def targets(exprs):
    return [{"datasource": DS, "expr": e, "legendFormat": leg, "refId": chr(65 + i), "instant": False}
            for i, (e, leg) in enumerate(exprs)]


def ts(title, exprs, x, y, w, h, unit="percentunit", desc="", mn=None, mx=None, stack=False, fill=10):
    custom = {"drawStyle": "line", "lineWidth": 2, "fillOpacity": fill, "showPoints": "never", "spanNulls": True}
    if stack:
        custom["stacking"] = {"mode": "normal", "group": "A"}
    d = {"unit": unit, "custom": custom}
    if mn is not None:
        d["min"] = mn
    if mx is not None:
        d["max"] = mx
    return {"id": _nid(), "type": "timeseries", "title": title, "description": desc, "datasource": DS,
            "gridPos": {"x": x, "y": y, "w": w, "h": h}, "targets": targets(exprs),
            "fieldConfig": {"defaults": d, "overrides": []},
            "options": {"legend": {"displayMode": "list", "placement": "bottom"}, "tooltip": {"mode": "multi"}}}


def stat(title, expr, x, y, w, h, unit="percentunit", desc="", decimals=None, mn=None, mx=None, kind="stat"):
    d = {"unit": unit, "color": {"mode": "thresholds"}, "thresholds": {"mode": "absolute", "steps": [{"color": "blue", "value": None}]}}
    if decimals is not None:
        d["decimals"] = decimals
    if mn is not None:
        d["min"] = mn
    if mx is not None:
        d["max"] = mx
    return {"id": _nid(), "type": kind, "title": title, "description": desc, "datasource": DS,
            "gridPos": {"x": x, "y": y, "w": w, "h": h}, "targets": targets([(expr, "")]),
            "fieldConfig": {"defaults": d, "overrides": []},
            "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "colorMode": "value",
                        "graphMode": "area", "textMode": "auto"}}


def bars(title, expr, legend, x, y, w, h, unit="percentunit", desc="", mn=None, mx=None):
    d = {"unit": unit, "color": {"mode": "continuous-BlYlRd"}}
    if mn is not None:
        d["min"] = mn
    if mx is not None:
        d["max"] = mx
    return {"id": _nid(), "type": "bargauge", "title": title, "description": desc, "datasource": DS,
            "gridPos": {"x": x, "y": y, "w": w, "h": h},
            "targets": [{"datasource": DS, "expr": expr, "legendFormat": legend, "refId": "A", "instant": True}],
            "fieldConfig": {"defaults": d, "overrides": []},
            "options": {"orientation": "horizontal", "displayMode": "gradient", "showUnfilled": True,
                        "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}}}


def text(title, md, x, y, w, h):
    return {"id": _nid(), "type": "text", "title": title, "gridPos": {"x": x, "y": y, "w": w, "h": h},
            "options": {"mode": "markdown", "content": md}}


def mix(dim, title, x, y, w, h):
    q = (f'sum by ({dim}) (increase(rlcache_action_total{{policy="$policy"}}[30s])) '
         f'/ scalar(sum(increase(rlcache_action_total{{policy="$policy"}}[30s])))')
    return ts(title, [(q, f"{{{{{dim}}}}}")], x, y, w, h, unit="percentunit", mn=0, mx=1, stack=True, fill=60,
              desc=f"Share of the chosen actions by {dim} over the last 30 s, for the policy picked in the drop-down above.")


def table_recent(x, y, w, h):
    expr = (f'rlcache_recent_decision{{policy="{AGENT}"}} == on(policy) group_left '
            f'rlcache_recent_batch{{policy="{AGENT}"}}')
    excl = {k: True for k in ("Time", "Value", "__name__", "instance", "job", "batch", "policy", "choice")}
    order = ["seq", "sim_time", "key", "size_bytes", "placement", "ttl_s", "priority", "q_score", "confidence"]
    return {"id": _nid(), "type": "table", "title": "Decision log: what the model chose for the latest cache misses (newest first)",
            "description": "Each row is one cache miss. The model read the 19 inputs and picked where to store the item, how long to keep it (TTL) and its eviction priority. q_score = how good the model thinks this action is; confidence = share of the top action.",
            "datasource": DS, "gridPos": {"x": x, "y": y, "w": w, "h": h},
            "targets": [{"datasource": DS, "expr": expr, "format": "table", "instant": True, "refId": "A"}],
            "transformations": [
                {"id": "convertFieldType", "options": {"conversions": [
                    {"targetField": "seq", "destinationType": "number"}, {"targetField": "key", "destinationType": "number"},
                    {"targetField": "size_bytes", "destinationType": "number"}, {"targetField": "ttl_s", "destinationType": "number"}]}},
                {"id": "sortBy", "options": {"fields": {}, "sort": [{"field": "seq", "desc": True}]}},
                {"id": "organize", "options": {"excludeByName": excl, "indexByName": {n: i for i, n in enumerate(order)},
                                               "renameByName": {"seq": "#", "sim_time": "sim time (m:ss)", "key": "key id", "size_bytes": "size (bytes)",
                                                                "placement": "store in", "ttl_s": "keep for (s)", "priority": "eviction priority",
                                                                "q_score": "score (Q)", "confidence": "confidence"}}}],
            "fieldConfig": {"defaults": {"custom": {"align": "left"}}, "overrides": []},
            "options": {"showHeader": True, "cellHeight": "sm"}}


panels = []
y = 0
panels.append(text("How to read this", (
    "**What you see:** the trained reinforcement-learning model and four simple rules replay the SAME stream of cache requests in the simulator, "
    "side by side, in fast-forward. Every cache miss makes the policy choose one of 45 actions (how long to keep the item, how protected it is, "
    "where to store it). Lines higher on *hit ratio* and *utility* and lower on *stale reads* are better. "
    "*Utility U* = hits + 0.5 x speed score - 3 x stale cost (the project's selection score). Data may be SYNTHETIC or a real Twitter sample "
    "(see the info panel). Pick a policy in the **policy** drop-down to see its action mix."), 0, y, 24, 3))
y += 3
panels.append(stat("Hit ratio now (model)", f'rlcache_window_hit_ratio{{policy="{AGENT}"}}', 0, y, 4, 4, desc="Reads served from the cache in the last ~10 s."))
panels.append(stat("Stale reads now (model)", f'rlcache_window_stale_rate{{policy="{AGENT}"}}', 4, y, 4, 4, desc="Reads that returned an out-of-date copy."))
panels.append(stat("Utility now (model)", f'rlcache_window_utility{{policy="{AGENT}"}}', 8, y, 4, 4, unit="none", decimals=3))
panels.append(stat("Replay progress", f'rlcache_progress_fraction{{policy="{AGENT}"}}', 12, y, 4, 4, kind="gauge", mn=0, mx=1))
panels.append(stat("Decisions per second (model)", f'sum(rate(rlcache_decisions_total{{policy="{AGENT}"}}[10s]))', 16, y, 4, 4, unit="ops",
                   desc="Cache misses per real second that needed a decision (fast-forwarded)."))
panels.append(stat("Simulated time", f'rlcache_sim_time_seconds{{policy="{AGENT}"}}', 20, y, 4, 4, unit="s", decimals=0))
y += 4
panels.append(table_recent(0, y, 24, 8))
y += 8
panels.append(ts("Hit ratio (higher is better)", [("rlcache_window_hit_ratio", "{{policy}}")], 0, y, 12, 8, mn=0, mx=1))
panels.append(ts("Stale reads (lower is better)", [("rlcache_window_stale_rate", "{{policy}}")], 12, y, 12, 8, mn=0))
y += 8
panels.append(ts("Utility U (higher is better)", [("rlcache_window_utility", "{{policy}}")], 0, y, 12, 8, unit="none"))
panels.append(ts("How full the caches are", [("rlcache_tier_utilisation", "{{policy}} - {{tier}}")], 12, y, 12, 8, mn=0, mx=1,
                 desc="Share of capacity used in the local (L1) and Redis (L2) tiers."))
y += 8
panels.append(mix("placement", "Where the chosen policy stores items", 0, y, 8, 8))
panels.append(mix("ttl", "How long it keeps them (TTL in seconds)", 8, y, 8, 8))
panels.append(mix("priority", "Eviction protection chosen", 16, y, 8, 8))
y += 8
panels.append(bars("What the model SEES: the 19 inputs at its last decision", f'rlcache_agent_feature{{policy="{AGENT}"}}', "{{feature}}",
                   0, y, 12, 12, unit="none", mn=-1, mx=1,
                   desc="Normalised values (about 0-1, some -1 to 1) of the 19 numbers describing the cache miss that was just decided."))
panels.append(bars("What the model THINKS: best score (Q) among the actions of each kind", f'rlcache_agent_q_group_max{{policy="{AGENT}"}}',
                   "{{dimension}} = {{choice}}", 12, y, 12, 12, unit="none",
                   desc="The model scores each of the 45 actions; this shows the best score within each placement, TTL and priority choice. Higher = preferred."))
y += 12
panels.append(ts("Model confidence", [(f'rlcache_agent_choice_confidence{{policy="{AGENT}"}}', "confidence (share of the top action)"),
                                       (f'rlcache_agent_q_entropy_norm{{policy="{AGENT}"}}', "indecision (1 = all actions look equal)")],
                 0, y, 8, 7, mn=0, mx=1))
panels.append(ts("Model scores", [(f'rlcache_agent_q_max{{policy="{AGENT}"}}', "best action score (Q)"),
                                  (f'rlcache_agent_q_spread{{policy="{AGENT}"}}', "gap between best and worst action")], 8, y, 8, 7, unit="none"))
panels.append(ts("Backend load (misses reaching the database per second)", [("sum by (policy) (rate(rlcache_backend_fetches_total[10s]))", "{{policy}}")],
                 16, y, 8, 7, unit="ops"))
y += 7
panels.append(bars("Whole replay so far: hit ratio", "rlcache_cum_hit_ratio", "{{policy}}", 0, y, 8, 7, mn=0, mx=1))
panels.append(bars("Whole replay so far: stale reads", "rlcache_cum_stale_rate", "{{policy}}", 8, y, 8, 7, mn=0))
panels.append(bars("Whole replay so far: utility U", "rlcache_cum_utility", "{{policy}}", 16, y, 8, 7, unit="none", mn=0))

dash = {
    "uid": "rl-cache-live", "title": "RL cache decision engine - live replay", "tags": ["rl-cache"], "timezone": "browser",
    "schemaVersion": 39, "version": 1, "editable": True, "refresh": "2s", "time": {"from": "now-5m", "to": "now"},
    "templating": {"list": [{
        "name": "policy", "label": "policy", "type": "query", "datasource": DS,
        "query": {"query": "label_values(rlcache_action_total, policy)", "refId": "p"}, "refresh": 2,
        "includeAll": False, "multi": False, "current": {"text": AGENT, "value": AGENT}, "sort": 1}]},
    "annotations": {"list": []}, "panels": panels,
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(dash, indent=1), encoding="utf-8")
print("wrote", OUT, len(panels), "panels")
