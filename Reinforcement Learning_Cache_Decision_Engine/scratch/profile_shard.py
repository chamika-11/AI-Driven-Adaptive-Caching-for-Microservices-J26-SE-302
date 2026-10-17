import sys, collections, statistics
path = sys.argv[1]
ops = collections.Counter(); n = 0; bad = 0
ts_min = None; ts_max = None
ttl_set = collections.Counter(); ttl_nonwrite_nonzero = 0
keys = set(); writes_per_key = collections.Counter()
with open(path, "r", encoding="utf-8", errors="replace") as f:
    for line in f:
        p = line.rstrip("\n").split(",")
        if len(p) != 7: bad += 1; continue
        n += 1
        t = int(p[0]); ts_min = t if ts_min is None else min(ts_min, t); ts_max = t if ts_max is None else max(ts_max, t)
        op = p[5]; ops[op] += 1; ttl = int(p[6]); keys.add(p[1])
        if op in ("set","add","replace","cas"): ttl_set[ttl] += 1
        if op in ("get","gets") and ttl != 0: ttl_nonwrite_nonzero += 1
        if op not in ("get","gets"): writes_per_key[p[1]] += 1
print(path.split("/")[-1].split("\\")[-1], "rows", n, "bad", bad, "ts", ts_min, ts_max, "span_h", round((ts_max-ts_min)/3600,2), "unique_keys", len(keys))
print(" ops", dict(ops.most_common()))
print(" write_frac", round(sum(v for k,v in ops.items() if k not in ('get','gets'))/n,3))
print(" top set-TTLs", ttl_set.most_common(8), "read_rows_with_nonzero_ttl", ttl_nonwrite_nonzero)
w = sorted(writes_per_key.values())
if w: print(" keys_written", len(w), "writes/key p50", w[len(w)//2], "p90", w[int(len(w)*.9)], "max", w[-1])
