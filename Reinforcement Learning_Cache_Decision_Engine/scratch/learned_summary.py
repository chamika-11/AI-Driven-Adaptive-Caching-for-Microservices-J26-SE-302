import sys, json; sys.path.insert(0, "src")
import numpy as np
from rlcache.analysis import report as R
df = R.load_rows("results/results.csv")
print("rows:", len(df), " learned rows:", int((df.policy_class == "learned").sum()))
out = {}
for cap in (0.01, 0.05, 0.25):
    print(f"\n=== capacity {cap}: test slice, paired by seed (n=10) ===")
    for v in ("tabq:qbin", "tabq:ewidth", "tabq:bandit"):
        r = R.learned_vs_baselines(df, v, "harsh", cap)
        out[f"{v}@{cap}"] = r
        lo, hi = r["delta_ohr_ci"]
        line = (f"{v:<12} dOHR vs envelope {100*r['delta_ohr_mean']:+.2f} pp [{100*lo:+.2f}, {100*hi:+.2f}] "
                f"above-envelope {r['n_above_envelope']}/10, beyond-frontier {r['n_beyond_frontier']}/10")
        print(line)
        for ref in ("random:45", "fixed:redis/3600s/normal", "place_size:p25"):
            m, l, h, w = r[f"d_utility_vs_{ref}"]
            mo, lo2, ho2, wo = r[f"d_ohr_vs_{ref}"]
            ms, ls, hs, ws = r[f"d_stale_read_rate_vs_{ref}"]
            print(f"      vs {ref:<26} dU {m:+.4f} [{l:+.4f},{h:+.4f}] {w}/10 | dOHR {100*mo:+.2f}pp {wo}/10 | dstale {100*ms:+.2f}pp {ws}/10")
Path = __import__("pathlib").Path
Path("results/tabq_eval_summary.json").write_text(json.dumps(out, indent=1, default=float))
