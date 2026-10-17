import pathlib
p = pathlib.Path("docs/M6_BASELINES.md"); s = p.read_text(encoding="utf-8")
def rep(a, b):
    global s
    assert s.count(a) == 1, a[:60]
    s = s.replace(a, b)
rep("""5. **The Belady bounds are far away** (0.56) and are loose by construction (unit-size objects,
   offline, and the baselines use a weak sampled-LRU): eviction/admission quality, not TTL or
   placement, accounts for most of the distance at small capacity. Strong eviction policies
   (SIEVE, S3-FIFO, W-TinyLFU) are M11 and would move all rows up.""",
"""5. **The Belady bounds are far away** (0.56 vs ≤ 0.36) and are loose by construction (unit-size
   objects, offline). The baselines all use a weak sampled-LRU eviction, so a large part of the
   distance is plausibly eviction/admission quality rather than TTL or placement — this was NOT
   measured (strong eviction policies — SIEVE, S3-FIFO, W-TinyLFU — are M11 and would move
   every row up).""")
rep("so it can outlive a write by the fetch\n  window.", "so it can outlive a write by up to the\n  fetch latency (tens of ms).")
p.write_text(s, encoding="utf-8")
