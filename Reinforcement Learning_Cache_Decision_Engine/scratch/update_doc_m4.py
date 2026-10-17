import pathlib

p = pathlib.Path("IMPLEMENTATION_DECISIONS.md")
s = p.read_text(encoding="utf-8")


def rep(old, new):
    global s
    n = s.count(old)
    assert n == 1, (n, old[:90])
    s = s.replace(old, new)


# ---- banner ---------------------------------------------------------------------------------
a = s.index("> **Status 2026-10-15:")
b = s.index("\n", a)
s = s[:a] + ("> **Status 2026-10-15: M0–M4 implemented and gated; M5 (features, reward, transitions) not started.** "
             "`pytest`: **128 passed** (`.venv`, Python 3.12.0, torch 2.14.1+cpu). The simulator runs and is "
             "invariant-tested, but there are still no feature values, reward, baselines, tabular Q or DQN, and "
             "no real-trace *experiment* has been run (see §2b, `docs/DATA_ACCESS.md`). Simulator behaviour "
             "evidence: `docs/M4_SIM_DIAGNOSTIC.md` (synthetic, one seed, not a result). A requirement is marked "
             "`DONE` only with the test that proves it named next to it.") + s[b:]

# ---- R-S rows ---------------------------------------------------------------------------------
rep("| R-S1 | Hand-written Python two-tier simulator (not libCacheSim PluginCache). | MD Correction 3 | NOT STARTED |",
    "| R-S1 | Hand-written Python two-tier simulator (not libCacheSim PluginCache). | MD Correction 3 | **DONE (`src/rlcache/sim/engine.py`; whole `tests/test_simulator.py`)** |")
rep("| R-S2 | Lookup order L1 → L2 → backend; per-tier TTL; promotion into L1 on L2 hit; writes invalidate (see C-6 for staleness model). | MD Phase 2 | NOT STARTED |",
    "| R-S2 | Lookup order L1 → L2 → backend; per-tier TTL; promotion into L1 on L2 hit; writes invalidate (see C-6 for staleness model). | MD Phase 2 | **DONE with a deviation (C-36)** (tests: `test_miss_then_fresh_l2_hit_and_byte_seconds`, `test_local_placement_hits_l1_only`, `test_promotion_flag_controls_placement_collapse`, staleness tests). Promotion is a flag, default OFF. |")
rep("| R-S3 | L1 ≈ an order of magnitude smaller than L2; tier-ratio sweep {1, 5, 10, 25}% later. | MD Phase 2, Phase 3 | NOT STARTED |",
    "| R-S3 | L1 ≈ an order of magnitude smaller than L2; tier-ratio sweep {1, 5, 10, 25}% later. | MD Phase 2, Phase 3 | **Ratio configurable and defaulted to 10% (test: `test_resolve_capacities_from_footprint`)**; the sweep is not run. |")
rep("| R-S4 | Decision point = cache miss that will populate a key (or write that repopulates). **Not per request.** | MD Decision cadence | NOT STARTED |",
    "| R-S4 | Decision point = cache miss that will populate a key (or write that repopulates). **Not per request.** | MD Decision cadence | **DONE for misses (tests: `test_every_insertion_is_closed_exactly_once`, `test_concurrent_misses_inside_fetch_window_are_real_misses_one_decision`)**. Writes do NOT repopulate (write-around, D-26). |")
rep("| R-S5 | Continuing formulation: `terminated` always False; window ends are `truncated`/reporting only; window boundaries never zero the bootstrap. | MD Decision cadence, RLCache | NOT STARTED |",
    "| R-S5 | Continuing formulation: `terminated` always False; window ends are `truncated`/reporting only; window boundaries never zero the bootstrap. | MD Decision cadence, RLCache | **PARTIAL** — the engine has no episodes and closes open insertions as `truncated` at run end (test `test_every_insertion_is_closed_exactly_once`); the `done`-flag handling is an M5/M9 concern. |")
rep("| R-S6 | Pending-transition mechanism: store (s, a, t_decision) + accumulators (hits, byte-seconds, backend fetches, stale reads); close at first of eviction / invalidation / expiry / hard cap 7200 s. | MD Credit assignment | NOT STARTED |",
    "| R-S6 | Pending-transition mechanism: store (s, a, t_decision) + accumulators (hits, byte-seconds, backend fetches, stale reads); close at first of eviction / invalidation / expiry / hard cap 7200 s. | MD Credit assignment | **Lifecycle + accumulators DONE (tests: `test_every_insertion_is_closed_exactly_once`, `test_counts_partition_reads_and_match_trace`, `test_hard_cap_closes_long_lived_insertion`, `test_ttl_only_serves_stale_with_correct_age_and_cost`)**; `(s, a, r, s')` assembly and the closure-time reward are M5. Closes when the LAST copy is gone (D-24). |")
rep("| R-S7 | Expiry detection by min-heap (so expiry is a terminal event even if the key is never re-read). | MD Credit assignment | NOT STARTED |",
    "| R-S7 | Expiry detection by min-heap (so expiry is a terminal event even if the key is never re-read). | MD Credit assignment | **DONE (tests: `test_never_read_entry_still_expires_at_its_expiry_time`, `test_expired_insertions_close_exactly_ttl_after_materialization`)**. Exact-time expiry, not a 1 Hz poll. |")
rep("| R-S10 | Eviction protection implemented as multiplier on the key's eviction score; base eviction policy pluggable (sampled-LRU now; SIEVE/S3-FIFO for ablation arm C). | MD Action space, Ablation C | NOT STARTED |",
    "| R-S10 | Eviction protection implemented as multiplier on the key's eviction score; base eviction policy pluggable (sampled-LRU now; SIEVE/S3-FIFO for ablation arm C). | MD Action space, Ablation C | **Multiplier + sampled-LRU DONE (tests: `test_priority_high_protects_an_older_entry`, `test_priority_low_makes_a_younger_entry_the_victim`)**. \"Pluggable\" is NOT done: only a config string exists, SIEVE/S3-FIFO are not implemented. |")
rep("| R-S11 | Byte-based capacity and utilisation (used bytes / capacity). | MD state #11, reward mem term | NOT STARTED |",
    "| R-S11 | Byte-based capacity and utilisation (used bytes / capacity). | MD state #11, reward mem term | **DONE (tests: `test_byte_usage_never_exceeds_capacity`, `test_capacity_eviction_closes_insertion_and_is_counted_separately`)**; invariants asserted in-run. |")
rep("| R-S12 | Three-way read classification fresh / stale / miss; staleness age recorded. | MD Metrics | NOT STARTED |",
    "| R-S12 | Three-way read classification fresh / stale / miss; staleness age recorded. | MD Metrics | **DONE (tests: `test_counts_partition_reads_and_match_trace`, `test_stale_age_measures_time_since_FIRST_superseding_write`, `test_stale_age_is_bounded_by_ttl_plus_fetch_window`)** |")
rep("| R-S13 | Capacity evictions and TTL expirations counted separately. | MD Metrics | NOT STARTED |",
    "| R-S13 | Capacity evictions and TTL expirations counted separately. | MD Metrics | **DONE (test: `test_expiry_is_exact_and_counted_as_ttl_expiration_not_eviction`)** |")
rep("| R-S14 | Backend load counted at the backend boundary, absolute and per 1,000 reads. | MD Metrics, Correction 6 | NOT STARTED |",
    "| R-S14 | Backend load counted at the backend boundary, absolute and per 1,000 reads. | MD Metrics, Correction 6 | **DONE for absolute counts (test: `test_counts_partition_reads_and_match_trace`: one fetch per missing read, writes counted separately)**; per-1k computed in `scripts/sim_grid.py`, not yet in results rows. |")
rep("| R-S15 | Latency model L1 = 1 µs, L2 = 300 µs (40 µs Unix-socket variant), backend 8 ms **declared unsourced**; sensitivity sweep {1, 8, 50} ms. | MD Phase 2 | NOT STARTED |",
    "| R-S15 | Latency model L1 = 1 µs, L2 = 300 µs (40 µs Unix-socket variant), backend 8 ms **declared unsourced**; sensitivity sweep {1, 8, 50} ms. | MD Phase 2 | **Constants in `LatencyConfig` and used by the engine**; sweep NOT run. Note C-37 (the latency term barely separates tiers). |")
rep("| R-S18 | Throughput logging over time (detects state accumulation / thermal throttling). | MD Phase 5, Risk register | NOT STARTED |",
    "| R-S18 | Throughput logging over time (detects state accumulation / thermal throttling). | MD Phase 5, Risk register | **DONE (test: `test_throughput_is_logged`)**; 70k–285k req/s measured (`docs/M4_SIM_DIAGNOSTIC.md`). |")
rep("| R-S19 | Stampede accounting (concurrent same-key fetches) — see C-20 for the sequential-simulator definition. | MD Reward | NOT STARTED |",
    "| R-S19 | Stampede accounting (concurrent same-key fetches) — see C-20 for the sequential-simulator definition. | MD Reward | **Counting DONE (tests: `test_concurrent_misses_inside_fetch_window_are_real_misses_one_decision`, `test_inflight_counts_open_fetch_windows`, `test_spread_timestamps_removes_false_same_second_stampede`)**; the reward term is M5. |")

# ---- decisions --------------------------------------------------------------------------------
rep("| D-18 | Proposed repository layout:",
    "| D-24 | An insertion owns up to two copies (placement `both`) and CLOSES WHEN ITS LAST COPY IS GONE; `first_reason`/`first_close_time` record the first terminal event. | The MD says \"first terminal event\" but a decision's outcome is not realised while a copy still serves hits; closing on the first copy's eviction would drop the other copy's hits and byte-seconds from the reward. | ACTIVE |\n"
    "| D-25 | Under `perfect` staleness a value that went stale during its own backend fetch is NOT inserted (insertion closed `invalidation`, zero copies). Under `lossy`/`ttl_only` it is inserted and is stale on arrival. | Otherwise `perfect` would not give stale = 0 and the gate would be untestable; the race is realistic for the other modes. | ACTIVE |\n"
    "| D-26 | The decision is taken at fetch START; the value becomes visible `backend_latency` later and carries the source version at fetch start; writes do not repopulate (write-around + invalidate, as in MD Phase 8). | Needed so concurrent misses (stampede, C-20) are real misses. The MD's \"write that repopulates\" decision point is therefore not modelled. | ACTIVE |\n"
    "| D-27 | Promotion on L2 hit is a flag, default OFF (C-36). Promoted copies inherit version and expiry, so promotion never extends an insertion's life. | Keeps `redis` and `both` distinct actions. | ACTIVE |\n"
    "| D-28 | Staleness rolls (`p_bypass`, `p_inv_l1`) are pre-drawn per REQUEST INDEX from the seed (common random numbers), independent of the policy; eviction sampling uses a separate stream. | Paired comparisons across policies see the same propagation luck, lowering variance. | ACTIVE |\n"
    "| D-29 | Real traces with 1-second timestamps are passed through `Trace.with_spread_timestamps()` before simulation. | Otherwise every same-second read of a key looks concurrent within an 8 ms fetch window. | ACTIVE |\n"
    "| D-18 | Proposed repository layout:")

# ---- contradictions -----------------------------------------------------------------------------
rep("| C-32 | Responsibility table:",
    "| C-36 | — (R-S2, MD Phase 2 semantics) | \"Promotion into L1 on an L2 hit\" together with a placement action {local, redis, both}. | With promotion always on, a `redis` decision becomes `both` after the first re-read, so INV-7's placement dimension collapses. Promotion is a config flag, default OFF (D-27); test `test_promotion_flag_controls_placement_collapse` shows the collapse. | RESOLVED (by flag) |\n"
    "| C-37 | — (MD reward table) | `L0` = p50 backend latency so `exp(−L/L0)` is ≈ 0.37 on a miss and ≈ 1.0 on a local hit; placement meant to trade latency against capacity and duplication. | `exp(−L/L0)` = 0.9999 (L1), 0.9632 (L2), 0.3679 (backend): L1 over L2 is worth `w_lat·0.037 = 0.018` per hit vs a staleness cost up to 3.0. In the simulator `both` is Pareto-dominated by `redis` (25% capacity, lossy: stale 9.1% vs 2.2% for +0.2 pp OHR) and `local` is capacity-starved (`docs/M4_SIM_DIAGNOSTIC.md`). The placement dimension may carry little learnable signal. | **OPEN — empirical question for M5/M6** (reward calibration; tier-ratio and L0 sweeps). \"Gains are in TTL, not placement\" would be a reportable outcome. |\n"
    "| C-32 | Responsibility table:")

# ---- M4 gate evidence in section 9 --------------------------------------------------------------------
rep("| M4 | Simulator engine: tiers, expiry heap, eviction w/ priority, staleness model, invalidation, accounting. **No RL yet.** | M1, M2, **Q-3** | Invariants: every insert closed exactly once; counts fresh+stale+miss = reads; with perfect invalidation stale = 0; byte usage ≤ capacity; deterministic under seed. | here |",
    "| M4 | Simulator engine: tiers, expiry heap, eviction w/ priority, staleness model, invalidation, accounting. **No RL yet.** | M1, M2, **Q-3** | Invariants: every insert closed exactly once; counts fresh+stale+miss = reads; with perfect invalidation stale = 0; byte usage ≤ capacity; deterministic under seed. | here — **GATE PASSED 2026-10-15** (`tests/test_simulator.py`, 41 tests; full suite 128 passed) |")

# ---- change log ----------------------------------------------------------------------------------------
s = s.rstrip("\n") + "\n" + (
    "| 2026-10-15 | **M4 implemented and gated.** New: `src/rlcache/sim/{engine,policy}.py`, `tests/test_simulator.py` "
    "(41 tests), `scripts/sim_grid.py`, `docs/M4_SIM_DIAGNOSTIC.md`; `CacheConfig` gained `l2_footprint_frac`, "
    "`promote_on_l2_hit`, `hard_cap_s`; `Trace.with_spread_timestamps()`. `pytest`: **128 passed**. Found while "
    "testing: (i) first run had 11 errors + 3 failures, all in my fixtures/expectations (write-volume guard "
    "rightly refused an over-written fixture; three tests ended before the last fetch materialised); (ii) one real "
    "engine gap, a write racing its own fetch left a stale value under `perfect` invalidation (D-25). Simulator "
    "diagnostics (synthetic, one seed): OHR 0.34→0.83 and stale 0→2.2% across the TTL ladder at 25% capacity; "
    "`both` dominated by `redis`; placement signal weak (C-37, OPEN). Next: M5 (feature tracker, normaliser, "
    "reward, pending-transition manager, Gymnasium adapter). |\n")
p.write_text(s, encoding="utf-8")
print("ok", len(s))
