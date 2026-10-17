import pathlib


def patch(path, pairs):
    p = pathlib.Path(path)
    s = p.read_text(encoding="utf-8")
    for old, new in pairs:
        assert s.count(old) == 1, (path, old[:70])
        s = s.replace(old, new)
    p.write_text(s, encoding="utf-8")


patch("src/rlcache/evaluation.py", [
    ("""              w_stale: float | None = None) -> "EvalContext":""",
     """              w_stale: float | None = None, base_eviction: str | None = None) -> "EvalContext":"""),
    ("""        if w_stale is not None:                         # Addendum M11-E (E2): reward weight only""",
     """        if base_eviction is not None:                   # Addendum M11-F: the agent's own simulator eviction
            cfg = dataclasses.replace(cfg, cache=dataclasses.replace(cfg.cache, base_eviction=base_eviction))
        if w_stale is not None:                         # Addendum M11-E (E2): reward weight only"""),
])

patch("scripts/run_dqn.py", [
    ("""def dqn_rows(ctx, variant: str, backend: str, ckpt_dir: Path | None, decisions=None,
             suffix: str = "") -> list[dict]:""",
     """def dqn_rows(ctx, variant: str, backend: str, ckpt_dir: Path | None, decisions=None,
             suffix: str = "", splits=("val", "test")) -> list[dict]:"""),
    ("""    for split in ("val", "test"):
        pol = T.GreedyDQNPolicy(res, ctx)""", """    for split in splits:
        pol = T.GreedyDQNPolicy(res, ctx)"""),
    ("""f"{variant}{suffix}_cap""", """f"{variant}{suffix}_cap"""),
])
patch("scripts/run_dqn.py", [
    ("""lambda c, p=pol: p)
        r = evaluate_sim_policy(ctx, spec, split, policy=pol)""",
     """lambda c, p=pol: p, eviction=ctx.cfg.cache.base_eviction)
        r = evaluate_sim_policy(ctx, spec, split, policy=pol)"""),
    ("""f"code={code_hash()}")
        rows.append(r)""", """f"base_eviction={ctx.cfg.cache.base_eviction} code={code_hash()}")
        rows.append(r)"""),
])

patch("src/rlcache/baselines/policies.py", [
    ("""def eviction_registry() -> list[Spec]:""",
     '''def s3fifo_reference_registry() -> list[Spec]:
    """Addendum M11-F: static references UNDER S3-FIFO eviction - fixed (redis | both) x TTL {30, 120, 600, 3600} s
    and the size-threshold placement rule."""
    out: list[Spec] = []
    for p in (REDIS, BOTH):
        for ti in (1, 2, 3, 4):
            a = encode_action(p, ti, NORMAL)
            out.append(Spec(f"evict:s3fifo/{PLACEMENTS[p]}/{TTL_BUCKETS_S[ti]}s", "evict", "heuristic",
                            lambda c, a=a: FixedActionPolicy(a), eviction="s3fifo"))
    out.append(Spec("place_size:p25@s3fifo", "place_size", "heuristic",
                    lambda c: SizePlacementPolicy(float(np.percentile(c.trace.size[:c.splits.fit_end], 25))),
                    eviction="s3fifo"))
    return out


def eviction_registry() -> list[Spec]:'''),
])
print("ok")
