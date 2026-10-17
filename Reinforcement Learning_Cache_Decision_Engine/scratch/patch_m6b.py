import pathlib


def edit(path, pairs):
    p = pathlib.Path(path)
    s = p.read_text(encoding="utf-8")
    for a, b in pairs:
        assert s.count(a) == 1, (path, s.count(a), a[:70])
        s = s.replace(a, b)
    p.write_text(s, encoding="utf-8")


edit("src/rlcache/baselines/policies.py", [
    ('''# ---- registry ------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Spec:
    name: str
    family: str
    policy_class: str                     # heuristic | bound
    make: Callable[["object"], object]    # (EvalContext) -> policy
''', '''# ---- placement-lattice baselines (docs/PREREGISTRATION.md, Addendum M6-B: POST-HOC) -------------
LOCAL = 0
PLACE_TTL_IDX = 3                                       # 600 s for every placement-rule policy


class HashPlacementPolicy:
    """A fixed fraction of keys (stable hash of the key id) go to `local`, the rest to `redis`:
    the simplest way to use L1 and L2 as DISJOINT capacity."""

    def __init__(self, frac: float):
        self.frac = float(frac)

    def decide(self, ctx) -> int:
        h = ((ctx.key * 2654435761) & 0xFFFFFFFF) / 4294967296.0
        return encode_action(LOCAL if h < self.frac else REDIS, PLACE_TTL_IDX, NORMAL)


class SizePlacementPolicy:
    """Objects no larger than ``threshold`` bytes go to `local`, larger ones to `redis`."""

    def __init__(self, threshold: float):
        self.threshold = float(threshold)

    def decide(self, ctx) -> int:
        return encode_action(LOCAL if ctx.size <= self.threshold else REDIS, PLACE_TTL_IDX, NORMAL)


class FreqPlacementPolicy:
    """`local` if the key was requested >= k times among the last ``window`` requests (history
    strictly before the decision request), else `redis`.  Fed through the simulator observer."""

    def __init__(self, k: int, window: int = 1000):
        self.k, self.window = int(k), int(window)
        self._ring: list[int] = []
        self._head = 0
        self._counts: dict[int, int] = {}

    def on_request(self, i, t, key, is_write, hit) -> None:
        if len(self._ring) == self.window:
            old = self._ring[self._head]
            c = self._counts[old] - 1
            if c:
                self._counts[old] = c
            else:
                del self._counts[old]
            self._ring[self._head] = key
        else:
            self._ring.append(key)
        self._head = (self._head + 1) % self.window
        self._counts[key] = self._counts.get(key, 0) + 1

    def decide(self, ctx) -> int:
        local = self._counts.get(ctx.key, 0) >= self.k
        return encode_action(LOCAL if local else REDIS, PLACE_TTL_IDX, NORMAL)


# ---- registry ------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Spec:
    name: str
    family: str
    policy_class: str                     # heuristic | bound
    make: Callable[["object"], object]    # (EvalContext) -> policy
    post_hoc: bool = False                # added after a development result (Addendum M6-B)
'''),
    ('''    if include_bounds:
        for p in (REDIS, BOTH):''', '''    for f in (0.10, 0.25, 0.50):
        out.append(Spec(f"place_hash:{f:.2f}", "place_hash", "heuristic",
                        lambda c, f=f: HashPlacementPolicy(f), post_hoc=True))
    for q in (25, 50, 75):
        out.append(Spec(f"place_size:p{q}", "place_size", "heuristic",
                        lambda c, q=q: SizePlacementPolicy(
                            float(np.percentile(c.trace.size[:c.splits.fit_end], q))), post_hoc=True))
    for k in (2, 3, 5):
        out.append(Spec(f"place_freq:k{k}", "place_freq", "heuristic",
                        lambda c, k=k: FreqPlacementPolicy(k), post_hoc=True))
    if include_bounds:
        for p in (REDIS, BOTH):'''),
])

edit("src/rlcache/evaluation.py", [
    ('''    sim = Simulator(ctx.trace, ctx.cfg, policy, l1_capacity_bytes=ctx.l1_bytes,
                    l2_capacity_bytes=ctx.l2_bytes, seed=ctx.seed, keep_closed=True,
                    record_latencies=True)''', '''    sim = Simulator(ctx.trace, ctx.cfg, policy, l1_capacity_bytes=ctx.l1_bytes,
                    l2_capacity_bytes=ctx.l2_bytes, seed=ctx.seed, keep_closed=True,
                    record_latencies=True,
                    observer=policy if hasattr(policy, "on_request") else None)'''),
    ('''        "staleness_mode": ctx.arm, "w_stale": ctx.cfg.reward.w_stale, "predictor_accuracy": 1.0,
    }''', '''        "staleness_mode": ctx.arm, "w_stale": ctx.cfg.reward.w_stale, "predictor_accuracy": 1.0,
        "notes": ("post-hoc: added after a dev-seed diagnostic, before evaluation seeds ran "
                  "(PREREGISTRATION M6-B)") if spec.post_hoc else "",
    }'''),
])

edit("src/rlcache/analysis/report.py", [
    ('''    fams = ["fixed", "random", "stat_ttl", "pred_ttl", "aimd"]
    colors = dict(zip(fams, ["#4c72b0", "#8c8c8c", "#55a868", "#c44e52", "#8172b2"]))''',
     '''    fams = ["fixed", "random", "stat_ttl", "pred_ttl", "aimd", "place_hash", "place_size", "place_freq"]
    colors = dict(zip(fams, ["#4c72b0", "#8c8c8c", "#55a868", "#c44e52", "#8172b2",
                             "#dd8452", "#937860", "#da8bc3"]))'''),
])

edit("tests/test_baselines_eval.py", [
    ('''    assert len(names) == len(set(names)) == 62
    fam = {f: sum(r.family == f for r in reg) for f in {r.family for r in reg}}
    assert fam == {"fixed": 45, "random": 1, "stat_ttl": 6, "pred_ttl": 2, "aimd": 4,
                   "oracle_ttl": 2, "belady": 2}
    assert sum(r.policy_class == "heuristic" for r in reg) == 58
    assert sum(r.policy_class == "bound" for r in reg) == 4
    assert B.registry(include_bounds=False).__len__() == 58''', '''    assert len(names) == len(set(names)) == 71
    fam = {f: sum(r.family == f for r in reg) for f in {r.family for r in reg}}
    assert fam == {"fixed": 45, "random": 1, "stat_ttl": 6, "pred_ttl": 2, "aimd": 4,
                   "oracle_ttl": 2, "belady": 2, "place_hash": 3, "place_size": 3, "place_freq": 3}
    assert sum(r.policy_class == "heuristic" for r in reg) == 67
    assert sum(r.policy_class == "bound" for r in reg) == 4
    assert B.registry(include_bounds=False).__len__() == 67
    post = {r.family for r in reg if r.post_hoc}
    assert post == {"place_hash", "place_size", "place_freq"}          # Addendum M6-B, nothing else'''),
    ('''# ---- Belady bounds vs a brute-force optimum''', '''def test_hash_size_freq_placement_rules():
    h = B.HashPlacementPolicy(0.25)
    local = [decode_action(h.decide(_Ctx(k))).placement == 0 for k in range(4000)]
    assert 0.2 < np.mean(local) < 0.3
    assert local == [decode_action(h.decide(_Ctx(k))).placement == 0 for k in range(4000)]  # stable
    assert all(decode_action(h.decide(_Ctx(k))).ttl_s == 600 for k in range(20))
    s = B.SizePlacementPolicy(500.0)
    c = _Ctx(0)
    c.size = 500
    assert decode_action(s.decide(c)).placement == 0
    c.size = 501
    assert decode_action(s.decide(c)).placement == 1
    f = B.FreqPlacementPolicy(k=2, window=5)
    c = _Ctx(7)
    assert decode_action(f.decide(c)).placement == 1                      # unseen -> redis
    for i, key in enumerate([7, 1, 7, 2, 3]):
        f.on_request(i, float(i), key, False, False)
    assert decode_action(f.decide(c)).placement == 0                      # 2 hits in window
    f.on_request(5, 5.0, 4, False, False)                                 # evicts the first 7
    assert decode_action(f.decide(c)).placement == 1


def test_partitioning_rules_use_both_tiers_unlike_any_fixed_action():
    from rlcache.trace.synthetic import generate_synthetic
    tr = generate_synthetic(WorkloadConfig(n_requests=6000, n_keys=200,
                                           write_interval_median_s=50_000.0, seed=1))
    cfg = dataclasses.replace(Config(), latency=LatencyConfig(backend_sigma=0.0))
    res = {}
    for name, pol in (("fixed_redis", FixedActionPolicy.of(1, 3)), ("hash", B.HashPlacementPolicy(0.25))):
        sim = Simulator(tr, cfg, pol, l1_capacity_bytes=20_000, l2_capacity_bytes=200_000, seed=0)
        sim.begin(0, len(tr), 0)
        used = [0, 0]
        while (ctx := sim.next_decision()) is not None:
            sim.commit(pol.decide(ctx))
            used[0], used[1] = max(used[0], sim.l1.used), max(used[1], sim.l2.used)
        res[name] = tuple(used)
    assert res["fixed_redis"][0] == 0 and res["fixed_redis"][1] > 0       # strands L1
    assert res["hash"][0] > 0 and res["hash"][1] > 0                      # uses both


# ---- Belady bounds vs a brute-force optimum'''),
    ('''def test_row_is_deterministic_and_utility_matches_definition(ctx):''', '''def test_post_hoc_rows_are_labelled(ctx):
    r = evaluate(ctx, _spec("place_hash:0.25"), "test")
    assert r["notes"].startswith("post-hoc") and r["family"] == "place_hash"
    assert evaluate(ctx, _spec("fixed:redis/600s/normal"), "test")["notes"] == ""
    r2 = evaluate(ctx, _spec("place_freq:k3"), "val")                  # observer-driven policy runs
    assert 0.0 < r2["share_local"] < 1.0 and r2["n_reads"] > 0


def test_row_is_deterministic_and_utility_matches_definition(ctx):'''),
    ('''    fams = {"fixed", "random", "stat_ttl", "oracle_ttl", "belady"}''',
     '''    fams = {"fixed", "random", "stat_ttl", "oracle_ttl", "belady", "place_hash"}'''),
    ('''    assert set(sel) == {"fixed", "random", "stat_ttl"}''',
     '''    assert set(sel) == {"fixed", "random", "stat_ttl", "place_hash"}'''),
    ('''    assert {"fixed", "random", "stat_ttl"} <= {p.split(" -> ")[0] for p in t.policy if " -> " in p}''',
     '''    assert {"fixed", "random", "stat_ttl", "place_hash"} <= {p.split(" -> ")[0] for p in t.policy
                                                              if " -> " in p}'''),
])
print("patched")
