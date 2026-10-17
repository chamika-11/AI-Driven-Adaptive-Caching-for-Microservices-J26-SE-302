import sys; sys.path.insert(0, "src")
import pandas as pd
from rlcache.analysis.report import load_rows
df = load_rows("results/tabq_dev.csv")
pd.set_option("display.width", 220); pd.set_option("display.float_format", lambda x: f"{x:.3f}")
v = df[(df.split == "val")]
cols = ["capacity_frac", "policy", "ohr", "stale_read_rate", "share_local", "share_redis", "share_both",
        "ttl_median_s", "action_entropy_norm", "cap_evictions_per_1k", "ttl_expirations_per_1k"]
g = v[v.policy.str.startswith(("tabq", "random", "fixed:redis/3600"))].groupby(["capacity_frac", "policy"])[cols[2:]].mean()
print(g.to_string())
print()
q = v[(v.policy == "tabq:qbin")]
for cap in (0.01, 0.25):
    r = q[q.capacity_frac == cap].sort_values("seed")
    print("cap", cap, "per-seed U:", [round(x, 3) for x in r.utility], "OHR:", [round(x, 3) for x in r.ohr])
n = q[q.capacity_frac == 0.25].notes.iloc[0]
print(n)
