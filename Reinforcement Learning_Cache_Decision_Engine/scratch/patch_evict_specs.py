import pathlib

p = pathlib.Path("src/rlcache/baselines/policies.py")
s = p.read_text(encoding="utf-8")


def rep(old, new):
    global s
    assert s.count(old) == 1, old[:80]
    s = s.replace(old, new)


rep("""    post_hoc: bool = False                # added after a development result (Addendum M6-B)
""", """    post_hoc: bool = False                # added after a development result (Addendum M6-B)
    eviction: str = "sampled_lru"         # base eviction of the tiers (Addendum M11-E, E1)
""")
s += '''

def eviction_registry() -> list[Spec]:
    """Addendum M11-E (E1): fixed (placement, 3600 s, normal) under exact LRU / FIFO / SIEVE / S3-FIFO.
    Kept apart from :func:`registry`, whose 71 points are frozen (M6-3)."""
    ttl_idx = len(TTL_BUCKETS_S) - 1
    out: list[Spec] = []
    for pol in ("lru", "fifo", "sieve", "s3fifo"):
        for p in (REDIS, BOTH):
            a = encode_action(p, ttl_idx, NORMAL)
            out.append(Spec(f"evict:{pol}/{PLACEMENTS[p]}/{TTL_BUCKETS_S[ttl_idx]}s", "evict", "heuristic",
                            lambda c, a=a: FixedActionPolicy(a), eviction=pol))
    return out
'''
p.write_text(s, encoding="utf-8")

p = pathlib.Path("src/rlcache/evaluation.py")
s = p.read_text(encoding="utf-8")
rep("""    policy = policy if policy is not None else spec.make(ctx)
    sim = Simulator(ctx.trace, ctx.cfg, policy, l1_capacity_bytes=ctx.l1_bytes,""",
    """    policy = policy if policy is not None else spec.make(ctx)
    cfg = ctx.cfg
    if spec.eviction != cfg.cache.base_eviction:
        cfg = dataclasses.replace(cfg, cache=dataclasses.replace(cfg.cache, base_eviction=spec.eviction))
    sim = Simulator(ctx.trace, cfg, policy, l1_capacity_bytes=ctx.l1_bytes,""")
rep("""        "notes": ("post-hoc: added after a dev-seed diagnostic, before evaluation seeds ran "
                  "(PREREGISTRATION M6-B)") if spec.post_hoc else "",""",
    """        "notes": ("post-hoc: added after a dev-seed diagnostic, before evaluation seeds ran "
                  "(PREREGISTRATION M6-B)") if spec.post_hoc else (
                      f"base_eviction={spec.eviction} (Addendum M11-E)" if spec.eviction != "sampled_lru" else ""),""")
p.write_text(s, encoding="utf-8")
print("ok")
