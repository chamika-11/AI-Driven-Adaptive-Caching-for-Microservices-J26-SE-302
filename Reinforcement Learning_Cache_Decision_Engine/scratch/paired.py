import sys; sys.path.insert(0, "src")
import numpy as np, pandas as pd
from rlcache.analysis.report import load_rows
df = load_rows("results/results.csv")
t = df[df.split == "test"]
def piv(cap, pol, col): 
    g = t[(t.capacity_frac == cap) & (t.policy == pol)].sort_values("seed")
    return g[col].to_numpy()
def paired(cap, a, b, col="ohr"):
    d = piv(cap, a, col) - piv(cap, b, col)
    se = d.std(ddof=1) / np.sqrt(len(d))
    return d.mean(), d.std(ddof=1), se, int((d > 0).sum())
rows = [
 (0.01, "place_size:p25", "fixed:redis/3600s/normal", "ohr"),
 (0.01, "place_size:p25", "random:45", "ohr"),
 (0.01, "place_hash:0.10", "fixed:redis/3600s/normal", "ohr"),
 (0.01, "random:45", "fixed:redis/3600s/normal", "ohr"),
 (0.01, "place_size:p25", "fixed:redis/3600s/normal", "stale_read_rate"),
 (0.05, "place_size:p25", "fixed:redis/3600s/normal", "ohr"),
 (0.25, "zerostale_oracle_ttl:redis", "stat_ttl:p10/redis", "ohr"),
 (0.25, "zerostale_oracle_ttl:redis", "stat_ttl:p10/redis", "stale_read_rate"),
 (0.25, "zerostale_oracle_ttl:redis", "fixed:redis/30s/normal", "ohr"),
 (0.25, "zerostale_oracle_ttl:redis", "fixed:redis/30s/normal", "stale_read_rate"),
 (0.25, "fixed:redis/3600s/normal", "stat_ttl:p10/redis", "ohr"),
]
print(f"{'cap':>5} {'A':<28}{'B':<28}{'metric':<17}{'mean(A-B)':>11}{'sd':>9}{'se':>9}{'A>B':>5}")
for cap, a, b, col in rows:
    m, sd, se, w = paired(cap, a, b, col)
    print(f"{cap:5.2f} {a:<28}{b:<28}{col:<17}{m:11.4f}{sd:9.4f}{se:9.4f}{w:4d}/10")
# stale sd across seeds relative to mean for fixed redis 3600 at each capacity
for cap in (0.01, 0.05, 0.25):
    x = piv(cap, "fixed:redis/3600s/normal", "stale_read_rate")
    print(cap, "fixed redis/3600 stale% per seed:", np.round(100 * x, 2).tolist())
