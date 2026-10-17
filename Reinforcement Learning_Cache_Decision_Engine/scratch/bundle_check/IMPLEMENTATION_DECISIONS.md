# IMPLEMENTATION_DECISIONS.md — RL Cache Decision Engine (J26-SE-302, Component 1)

Owner: Thennakoon T.M.N.C. (IT23286764) · Supervisor: Mr. Jagath Wickramaratne
Created: 2026-10-14 · Sources: `DQN cache decision engine build.md` (the "MD", final research specification) and `IT23286764_PP.pdf` (the "Proposal").

> **Status 2026-10-15: M0–M8 done; M9 (DQN) is BLOCKED by C-47 (PyTorch cannot be imported on this machine: Windows Application Control, WinError 4551).** `pytest`: **211 passed** (`.venv`, Python 3.12.0). One learned agent exists: tabular Q-learning (M8). On the evaluation seeds it beats random at the primary 1% capacity, statistically TIES a one-line size-threshold rule there, is below the baseline frontier at 5%, and (γ = 0.95) collapses at 25%. INV-8 (Pareto dominance) is NOT supported by any agent so far. Non-learned baselines and tabular Q were each evaluated ONCE on evaluation seeds 0–9 (`results/results.csv`, `harsh` arm, three capacities, synthetic only). Pre-registrations: `docs/PREREGISTRATION.md` (M6, post-hoc M6-B, M7, M8, M8-a). No real-trace *experiment* has been run (§2b, `docs/DATA_ACCESS.md`). Evidence: `docs/M4_SIM_DIAGNOSTIC.md`, `docs/PLACEMENT_SIGNAL.md`, `docs/REWARD_SCALING.md`, `docs/M6_BASELINES.md`, `docs/M7_SIGNAL_TEST.md`, `docs/M8_TABULAR_Q.md`. A requirement is marked `DONE` only with the test that proves it named next to it.

How to use this file: every decision gets a `D-` id, every contradiction a `C-` id, every assumption an `A-` id, every open question a `Q-` id, every requirement an `R-` id. When code changes a decision, update the entry and add a line to the change log (§10). Never delete an entry; mark it `SUPERSEDED by D-xx`.

---

## 1. Fixed research invariants (must not change)

These come from the user's instruction and the MD's final specification. Any implementation choice that would violate one is rejected, not traded off.

| ID | Invariant |
|---|---|
| INV-1 | State = **19 features**, exactly as MD §"State vector: 19 dimensions" (10 per-key, 8 cache-wide, 1 predictor flag). No key identity. Hit ratio only, never also miss ratio. |
| INV-2 | Action = **flat `Discrete(45)`** = 5 TTL buckets × 3 eviction-protection levels × 3 placement tiers. Encoding `a = p*15 + t*3 + e`. |
| INV-3 | Learner = **Double Dueling DQN** (hand-written PyTorch; SB3 used only as a correctness oracle). |
| INV-4 | Reward = **multi-objective**: hit, latency, staleness (proportional to stale age), backend load (relative to no-cache), memory byte-seconds, utilisation gate, stampede. |
| INV-5 | The agent makes **TTL decisions** (buckets {5, 30, 120, 600, 3600} s). |
| INV-6 | The agent sets **eviction protection** (low / normal / high). |
| INV-7 | The agent chooses **placement**: local sidecar / Redis / both. |
| INV-8 | Headline claim is **Pareto dominance in (hit ratio, stale-read rate)** from the joint TTL+placement decision at equal capacity and equal eviction policy — not a scalar win over LRU. |
| INV-9 | Q-learning (tabular, discretised) remains the RL baseline from the Proposal (Objective 2, FR8), presented as an ablation of the method. |

---

## 2. Environment facts (verified 2026-10-14)

| Check | Result | Consequence |
|---|---|---|
| Existing project code in the cloud workspace | **None.** Only the two source documents are present. | There is no prior implementation to inspect. "Prototype code" in this file means the code blocks inside the MD (C-section). |
| Folder on the user's PC (Windows, device "msi") | **No folder connected.** | If a local project folder exists, it has not been inspected. See Q-1. |
| Python in cloud workspace | 3.13.16; numpy 2.5.3, pandas 3.0.5, pydantic 2.13.5 present | Simulator, trace and baseline code can be built and tested here. |
| `pip install gymnasium libcachesim rliable` (clean venv) | **Succeeded**: gymnasium 1.4.0, libcachesim 0.3.5 | Phase-2/3 tooling is available here. |
| `pip install torch` (PyTorch CPU index) | **Failed**: proxy 403 on download.pytorch.org | — |
| `pip install torch` (PyPI) | **Failed**: killed by 560 s timeout | **No DQN code can be executed in this workspace.** DQN tests must run on the user's machine (D-3). |
| `curl ftp://ftp.pdl.cmu.edu/.../open_source/` | Returned no listing | Twitter plain-text trace **not reachable from here**; must be attempted from the user's connection (R-D1, Q-2). |
| docker, redis-server, psql binaries | Present in cloud workspace | Phase 8 components could be smoke-tested here later; not needed for the first build. |
| User PC | Windows x64; a `vscode-remote-wsl` folder exists, suggesting WSL | libcachesim wheels need glibc ≥ 2.34 (Linux) or macOS 15 ARM — **no Windows wheel is documented**, so run under WSL2 (A-12). |

### 2b. Environment facts verified 2026-10-15 on the user's PC (supersede the cloud-workspace rows above)

| Check | Result | Consequence |
|---|---|---|
| Python | 3.12.0 (Windows, `.venv` in project root) | — |
| `pip install` torch 2.14.1 (CPU wheel), gymnasium 1.4.0, numpy 2.5.4, pandas 3.0.6, scipy, zstandard, tensorboard | **Succeeded** (first attempt failed on a transient DNS error for `files.pythonhosted.org`; retry succeeded) | **D-3 is SUPERSEDED**: DQN code can be executed and tested on this machine. |
| CMU PDL FTP | Reachable, but `twemcacheWorkload` is a **dangling symlink** (`550 No such file or directory`) | Full shards unobtainable via the documented path. |
| SNIA IOTTA | Anti-bot JS challenge + licence acceptance | Needs the owner in a browser. |
| `twitter/cache-trace` repo `samples/2020Mar/` | **Reachable**; cluster012 / cluster052 / cluster022 downloaded (66 / 44 / 74 MB, plain text) | Schema proven (R-D1). Samples are 1M rows spanning only 58–553 s (not usable for TTL-expiry or per-key volatility experiments). |
| libcachesim, rliable, d3rlpy | **Not installed** on this machine | Needed from M11 / M12 only. |

---

## 3. Requirements register

Status values: `NOT STARTED` · `IN PROGRESS` · `DONE (test: <name>)` · `DEFERRED` · `DROPPED (reason)`. Source: MD section or Proposal FR/NFR/Objective.

### 3.1 Data and traces (R-D)

| ID | Requirement | Source | Status |
|---|---|---|---|
| R-D1 | Obtain one plain-text Twitter Twemcache shard with `op` and `TTL` columns (CMU PDL FTP → SNIA IOTTA → repo `samples/`); prove with 5 printed rows, nonzero TTL on `set`. | MD Correction 1, Phase 0 | **DONE for the schema, via repo `samples/` only** (test: `test_real_cluster012_prefix_schema`; 5 rows printed by `scripts/profile_trace.py`; evidence `docs/DATA_ACCESS.md`). Full shards: BLOCKED (FTP symlink dangling; SNIA needs browser + licence). |
| R-D2 | Never decompress a whole shard; stream in chunks; slice contiguous time windows. | MD Phase 0/1 | **DONE (tests: `test_time_window_and_early_stop`, `test_zstd_stream_matches_plain`, `test_max_rows`)**. Early stop at `t_end` and `.zst` streaming verified on fixtures; never exercised on a real multi-GB `.zst` (none available). |
| R-D3 | Streaming parser for schema `ts,key,key_size,val_size,client_id,op,ttl`; 11-op vocabulary; write set = {set, add, replace, cas, append, prepend, incr, decr, delete}. | MD Phase 1 | **DONE (tests: `test_all_eleven_operations_recognised`, `test_read_write_classification`, `test_namespace_delimiter_inference_not_always_colon`, `test_malformed_rows_counted_and_limit_enforced`)**. Delimiter inference also checked by hand on the real keys: cluster012 hashed → none, cluster052 `:`, cluster022 `|`. |
| R-D4 | Forward-fill last write's TTL onto later reads as `ttl_label`. | MD Phase 1 | **DONE (test: `test_ttl_label_forward_fill_is_causal`)** — causal (uses only earlier writes). |
| R-D5 | Sampling only by contiguous time window or key-space hash sampling **with capacity scaled by the same fraction**; never uniform row sampling. | MD Phase 1 | **DONE (test: `test_key_hash_sampling_keeps_whole_keys_and_records_fraction`)**. `scaled_capacity()` exists; the simulator must call it (M4). |
| R-D6 | Primary training trace cluster12 (write-heavy); evaluation cluster52 (fallback cluster22); one daytime-peak and one overnight window. | MD "Data" | **BLOCKED** — only 1–9 minute samples obtained; daytime/overnight windows need the full shards (Q-2). Parser ready. |
| R-D7 | Synthetic generator: truncated Zipf α ∈ {0.6, 0.8, 0.99, 1.2}; ~0.3 probability temporal-locality redraw from last ~1000 keys; **per-key lognormal write rate**; diurnal, flash-crowd, popularity-shift, write-rate-shift injectors. | MD "Data", Adaptation | **DONE (tests: `test_per_key_write_rate_spread`, `test_zipf_alpha_controls_skew`, `test_temporal_locality_increases_window_reuse`, `test_popularity_shift_changes_hot_set`, `test_flash_crowd_concentrates_traffic`, `test_write_rate_shift_multiplies_writes`, `test_time_to_next_write_spans_ttl_decades`)**. Diurnal is a sinusoidal arrival intensity; its effect has no dedicated test yet. |
| R-D8 | `oracleGeneral` files used only for Belady bounds, never as input features. | MD Correction 1 | NOT STARTED |
| R-D9 | Oracle annotations: `next_access_vtime` and `next_write_vtime` per request (two-pass), for Belady, TTL oracle, TTL-constrained Belady. | MD Phase 3 | **DONE (test: `test_oracle_matches_brute_force_on_small_trace`)**; Belady/TTL-Belady consumers not yet built. |
| R-D10 | Verify volatility varies across keys (distribution plot); if near-constant, switch to a write-heavier cluster. | MD Phase 1 | **Synthetic: DONE (test: `test_fitted_volatility_varies_across_keys`). Real: FAILS on the samples** — median 1 write per key in cluster012/052 (`docs/DATA_ACCESS.md`); needs the full shards. No plot produced yet. |
| R-D11 | (Optional) validate simulator hit-rate computation against Wikimedia `X_Cache` / Tencent `cache_hit` labels. | MD "Data" | DEFERRED |

### 3.2 Predictor stand-in and leakage control (R-P)

| ID | Requirement | Source | Status |
|---|---|---|---|
| R-P1 | `compute_volatility` (0.5·squashed write rate + 0.3·write ratio + 0.2·CV of inter-write gaps), declared as **this project's own** definition. | MD Phase 1 | **DONE (tests: `test_volatility_hand_computed_and_bounded`, `test_volatility_orders_keys_by_write_rate`)** |
| R-P2 | `compute_predicted_ttl` = 20th percentile of inter-write gaps, clipped [1, 3600]; never-written keys → 3600. | MD Phase 1 | **DONE (tests: `test_predicted_ttl_hand_computed`, `test_group_quantile_matches_numpy`)** |
| R-P3 | Frozen split: predictor statistics fitted on trace[0:30%], frozen; agent trained on later data; test touched once. | MD Correction 6, Evaluation | **Predictor part DONE (tests: `test_fit_ignores_everything_after_fit_end`, `test_fit_on_prefix_equals_fit_on_longer_trace`, `test_tables_are_frozen`)**; "test touched once" is a protocol enforced at M6/M10, not yet implemented. |
| R-P4 | `synthetic_predictor(accuracy)` interpolating truth with a **shuffled** copy (preserves marginal). | MD Phase 1 | **DONE with a deviation (C-33)** (tests: `test_accuracy_one_equals_truth`, `test_accuracy_zero_is_permutation_same_marginal`, `test_mixture_preserves_marginal_at_intermediate_accuracy`, `test_interpolate_mode_shrinks_variance_contradicting_md_claim`). Default is `mixture`, not the MD's literal interpolation. |
| R-P5 | Predictor-accuracy ablation over {0, 0.25, 0.5, 0.75, 1.0}, 3 seeds each. | MD Phase 6 | **DONE for the agent-free heuristic (M7, 10 dev seeds; `docs/M7_SIGNAL_TEST.md`, tests `tests/test_signal.py`)**; the learned-agent version is M11. |
| R-P6 | Agent fully functional with predictor absent (defaults). | MD contracts; Proposal NFR5 | **Tables DONE (test: `test_absent_predictor_is_constant_and_documented`)**; agent-level behaviour untested (no agent yet). |
| R-P7 | Normaliser statistics from training portion only; frozen at evaluation; shipped inside the checkpoint. | MD Correction 6, Overhead | **DONE for the normaliser (tests: `test_frozen_normalizer_does_not_change_and_round_trips`, `test_normalizer_is_learned_only_from_the_training_pass`)** — `state_dict()` round-trips; the checkpoint file format is M9. |
| R-P8 | Leakage test: no feature at decision time may depend on any request with index > current. | MD Correction 6; Proposal NFR9, Validation 7 | **DONE (tests: `test_no_feature_depends_on_future_requests`, `test_features_match_independent_brute_force_at_every_decision`, plus the R-P3 predictor tests)** — scrambling every request after a cut-off leaves all earlier observations bit-identical. |

### 3.3 Simulator / environment (R-S)

| ID | Requirement | Source | Status |
|---|---|---|---|
| R-S1 | Hand-written Python two-tier simulator (not libCacheSim PluginCache). | MD Correction 3 | **DONE (`src/rlcache/sim/engine.py`; whole `tests/test_simulator.py`)** |
| R-S2 | Lookup order L1 → L2 → backend; per-tier TTL; promotion into L1 on L2 hit; writes invalidate (see C-6 for staleness model). | MD Phase 2 | **DONE with a deviation (C-36)** (tests: `test_miss_then_fresh_l2_hit_and_byte_seconds`, `test_local_placement_hits_l1_only`, `test_promotion_flag_controls_placement_collapse`, staleness tests). Promotion is a flag, default OFF. |
| R-S3 | L1 ≈ an order of magnitude smaller than L2; tier-ratio sweep {1, 5, 10, 25}% later. | MD Phase 2, Phase 3 | **Ratio configurable and defaulted to 10% (test: `test_resolve_capacities_from_footprint`)**; the sweep is not run. |
| R-S4 | Decision point = cache miss that will populate a key (or write that repopulates). **Not per request.** | MD Decision cadence | **DONE for misses (tests: `test_every_insertion_is_closed_exactly_once`, `test_concurrent_misses_inside_fetch_window_are_real_misses_one_decision`)**. Writes do NOT repopulate (write-around, D-26). |
| R-S5 | Continuing formulation: `terminated` always False; window ends are `truncated`/reporting only; window boundaries never zero the bootstrap. | MD Decision cadence, RLCache | **DONE for assembly (tests: `test_no_transition_is_ever_terminal_and_window_ends_are_not_done`, `test_transition_assembly_invariants`)**: `done` is always False; end-of-run insertions are dropped and counted, never stored as terminal. The replay/target side (no bootstrap cut) is M9. |
| R-S6 | Pending-transition mechanism: store (s, a, t_decision) + accumulators (hits, byte-seconds, backend fetches, stale reads); close at first of eviction / invalidation / expiry / hard cap 7200 s. | MD Credit assignment | **DONE (tests: `test_transition_assembly_invariants`, M4 lifecycle tests)** — `(s, a, r, s')` assembled at closure; closes when the LAST copy is gone (D-24). |
| R-S7 | Expiry detection by min-heap (so expiry is a terminal event even if the key is never re-read). | MD Credit assignment | **DONE (tests: `test_never_read_entry_still_expires_at_its_expiry_time`, `test_expired_insertions_close_exactly_ttl_after_materialization`)**. Exact-time expiry, not a 1 Hz poll. |
| R-S8 | Monitoring queue: when chosen TTL is shorter than true lifetime, observe what longer TTL would have earned. | MD Credit assignment (RLCache) | **NOT STARTED — deferred** (needs counterfactual replay; revisit only if the plain agent fails to learn TTL ordering). |
| R-S9 | `s'` = global state at resolution time; semi-MDP; optional time-based discount (see C-17). | MD Credit assignment | **DONE as D-9 (test: `test_transition_assembly_invariants`)**: `s'` = observation at the next decision after closure; `dt` stored per transition for the D-11 ablation. |
| R-S10 | Eviction protection implemented as multiplier on the key's eviction score; base eviction policy pluggable (sampled-LRU now; SIEVE/S3-FIFO for ablation arm C). | MD Action space, Ablation C | **Multiplier + sampled-LRU DONE (tests: `test_priority_high_protects_an_older_entry`, `test_priority_low_makes_a_younger_entry_the_victim`)**. "Pluggable" is NOT done: only a config string exists, SIEVE/S3-FIFO are not implemented. |
| R-S11 | Byte-based capacity and utilisation (used bytes / capacity). | MD state #11, reward mem term | **DONE (tests: `test_byte_usage_never_exceeds_capacity`, `test_capacity_eviction_closes_insertion_and_is_counted_separately`)**; invariants asserted in-run. |
| R-S12 | Three-way read classification fresh / stale / miss; staleness age recorded. | MD Metrics | **DONE (tests: `test_counts_partition_reads_and_match_trace`, `test_stale_age_measures_time_since_FIRST_superseding_write`, `test_stale_age_is_bounded_by_ttl_plus_fetch_window`)** |
| R-S13 | Capacity evictions and TTL expirations counted separately. | MD Metrics | **DONE (test: `test_expiry_is_exact_and_counted_as_ttl_expiration_not_eviction`)** |
| R-S14 | Backend load counted at the backend boundary, absolute and per 1,000 reads. | MD Metrics, Correction 6 | **DONE for absolute counts (test: `test_counts_partition_reads_and_match_trace`: one fetch per missing read, writes counted separately)**; per-1k computed in `scripts/sim_grid.py`, not yet in results rows. |
| R-S15 | Latency model L1 = 1 µs, L2 = 300 µs (40 µs Unix-socket variant), backend 8 ms **declared unsourced**; sensitivity sweep {1, 8, 50} ms. | MD Phase 2 | **Constants in `LatencyConfig` and used by the engine**; sweep NOT run. Note C-37 (the latency term barely separates tiers). |
| R-S16 | Bounded per-key metadata (no unbounded `recency`/`freq` dicts). | MD Phase 5 diagnostics | **DONE (by construction; tests: `test_long_window_slides`)** — per-key arrays are O(n_keys), windows are fixed rings. Metadata bytes are not yet charged against capacity (R-E8). |
| R-S17 | Gymnasium-compatible adapter passing `check_env` (for API hygiene and SB3 cross-checks). | MD Phase 2 | **DONE (tests: `test_check_env_passes`, `test_env_reset_is_deterministic_and_obs_in_space`, `test_env_episode_semantics_and_reward_accounting`)**; reward semantics differ from textbook Gym on purpose (see `env.py` docstring, D-2). |
| R-S18 | Throughput logging over time (detects state accumulation / thermal throttling). | MD Phase 5, Risk register | **DONE (test: `test_throughput_is_logged`)**; 70k–285k req/s measured (`docs/M4_SIM_DIAGNOSTIC.md`). |
| R-S19 | Stampede accounting (concurrent same-key fetches) — see C-20 for the sequential-simulator definition. | MD Reward | **Counting DONE (tests: `test_concurrent_misses_inside_fetch_window_are_real_misses_one_decision`, `test_inflight_counts_open_fetch_windows`, `test_spread_timestamps_removes_false_same_second_stampede`)**; the reward term is M5. |

### 3.4 State (R-F) — the 19 features

**Names, order, blocks and the single as-of-timestamp convention are DONE** in `src/rlcache/features_spec.py` (tests: `test_exactly_19_features_in_three_blocks`, `test_no_miss_ratio_and_no_key_identity_features`, `test_tabular_feature_indices_fix_prototype_bug`, `test_state_ladder_is_strictly_nested`). **No feature VALUE is computed yet** — every row below stays `NOT STARTED` until the M5 tracker exists with hand-computed unit tests.

| # | Feature (normalisation) | Status |
|---|---|---|
| R-F1 | log recency gap 1, `log1p(Δt)/log1p(Δt_max)` clip [0,1] | **DONE** (hand-computed: `test_recency_gaps_and_sentinels`; cross-checked against an independent brute force by `test_features_match_independent_brute_force_at_every_decision` where applicable) |
| R-F2 | log recency gap 2, sentinel 1.0 if never seen | **DONE** (hand-computed: `test_recency_gaps_and_sentinels`; cross-checked against an independent brute force by `test_features_match_independent_brute_force_at_every_decision` where applicable) |
| R-F3 | count of this key in last 10 requests ÷ 10 | **DONE** (hand-computed: `test_window_counts_and_decision_request_excluded`; cross-checked against an independent brute force by `test_features_match_independent_brute_force_at_every_decision` where applicable) |
| R-F4 | count in last 100 ÷ 100 | **DONE** (hand-computed: `test_window_counts_and_decision_request_excluded`; cross-checked against an independent brute force by `test_features_match_independent_brute_force_at_every_decision` where applicable) |
| R-F5 | count in last 1000 ÷ 1000 | **DONE** (hand-computed: `test_window_counts_and_decision_request_excluded`, `test_long_window_slides`; cross-checked against an independent brute force by `test_features_match_independent_brute_force_at_every_decision` where applicable) |
| R-F6 | EDC, ~60 s half-life ÷ running max | **DONE** (hand-computed: `test_edc_decays_with_half_life`; cross-checked against an independent brute force by `test_features_match_independent_brute_force_at_every_decision` where applicable) |
| R-F7 | object size `log1p(bytes)/log1p(max)` | **DONE** (hand-computed: `test_sim_and_predictor_features_pass_through`; cross-checked against an independent brute force by `test_features_match_independent_brute_force_at_every_decision` where applicable) |
| R-F8 | backend fetch latency for this key (log-scaled) — see A-4 | **DONE** (hand-computed: `test_sim_and_predictor_features_pass_through`, `test_per_key_backend_latency_varies_and_is_seeded`; cross-checked against an independent brute force by `test_features_match_independent_brute_force_at_every_decision` where applicable) |
| R-F9 | predicted TTL `log1p/log1p(3600)` | **DONE** (hand-computed: `test_sim_and_predictor_features_pass_through`; cross-checked against an independent brute force by `test_features_match_independent_brute_force_at_every_decision` where applicable) |
| R-F10 | per-key write rate ("volatility") | **DONE** (hand-computed: `test_sim_and_predictor_features_pass_through`; cross-checked against an independent brute force by `test_features_match_independent_brute_force_at_every_decision` where applicable) |
| R-F11 | cache utilisation (bytes) | **DONE** (hand-computed: `test_sim_and_predictor_features_pass_through`; cross-checked against an independent brute force by `test_features_match_independent_brute_force_at_every_decision` where applicable) |
| R-F12 | hit ratio over last 1000 requests (**hit ratio only**) | **DONE** (hand-computed: `test_hit_ratio_counts_reads_only`; cross-checked against an independent brute force by `test_features_match_independent_brute_force_at_every_decision` where applicable) |
| R-F13 | request rate (log-scaled) | **DONE** (hand-computed: `test_rate_cov_and_invalidation_rate`; cross-checked against an independent brute force by `test_features_match_independent_brute_force_at_every_decision` where applicable) |
| R-F14 | rate CoV over 10 s | **DONE** (hand-computed: `test_rate_cov_and_invalidation_rate`; cross-checked against an independent brute force by `test_features_match_independent_brute_force_at_every_decision` where applicable) |
| R-F15 | rate CoV over 300 s | **DONE** (hand-computed: `test_cov300_uses_ten_second_sums`; cross-checked against an independent brute force by `test_features_match_independent_brute_force_at_every_decision` where applicable) |
| R-F16 | top-10-key share of last 1000 requests | **DONE** (hand-computed: `test_top10_share`; cross-checked against an independent brute force by `test_features_match_independent_brute_force_at_every_decision` where applicable) |
| R-F17 | global invalidation rate (log-scaled) | **DONE** (hand-computed: `test_rate_cov_and_invalidation_rate`; cross-checked against an independent brute force by `test_features_match_independent_brute_force_at_every_decision` where applicable) |
| R-F18 | normalised backend load (in-flight / max concurrency) — see C-20 | **DONE** (hand-computed: `test_inflight_counts_open_fetch_windows`, `test_sim_and_predictor_features_pass_through`; cross-checked against an independent brute force by `test_features_match_independent_brute_force_at_every_decision` where applicable) |
| R-F19 | hot-key flag from predictor {0,1} | **DONE** (hand-computed: `test_hot_flag_top_one_percent_and_tie_handling`; cross-checked against an independent brute force by `test_features_match_independent_brute_force_at_every_decision` where applicable) |
| R-F20 | Normalisation: running z-score clip [−5, 5] (Welford over EMA α≈1e-4) for unbounded features, fixed min-max for bounded; frozen at eval; declared own contribution. | **DONE (tests: `test_zscore_features_are_centered_and_clipped`, `test_frozen_normalizer_does_not_change_and_round_trips`, `test_observation_shape_names_and_ranges`)** — z-score (÷5) on backend latency, request rate, invalidation rate; running max on EDC and size; the rest fixed. |

### 3.5 Actions (R-A)

| ID | Requirement | Status |
|---|---|---|
| R-A1 | `encode_action(p,t,e) = p*15 + t*3 + e`; `decode_action` inverse; round-trip test over all 45. | **DONE (tests: `test_round_trip_all_digit_triples`, `test_round_trip_all_action_ids`, `test_stride_order_matches_spec`, range/type rejection tests)** |
| R-A2 | TTL buckets {5, 30, 120, 600, 3600} s (live demo variant: see C-23). | **DONE (test: `test_space_is_exactly_45`)** |
| R-A3 | Priority levels {low, normal, high} → eviction-score multipliers (values: A-6). | **Constants DONE (test: `test_cache_capacity_ratio`)**; multiplier effect on eviction needs M4. |
| R-A4 | Placement {local, redis, both}. | **Codec DONE (test: `test_decode_semantics` — local writes only L1, redis only L2)**; semantics inside the simulator pending (M4). |
| R-A5 | No admission ("do not cache") action; stated as scoped limitation. | **DONE (by construction: 45 actions, test `test_space_is_exactly_45`)** |
| R-A6 | Action masking hook (memory headroom, forbidding persist-like actions in Redis demo). | DEFERRED (demo) |

### 3.6 Reward (R-R)

| ID | Requirement | Status |
|---|---|---|
| R-R1 | `r = u·[w_hit·hit + w_lat·exp(−L/L0) − w_stale·min(1, stale_age/ttl) − w_backend·F/F_ref − w_mem·byte_s/(cap·T)] − w_stampede·max(0,c−1)/2.4`, aggregation per transition per D-10. | **DONE (tests: `test_reward_hand_computed`, `test_creating_miss_is_charged_only_through_the_backend_term`, `test_more_hits_raise_reward_monotonically`)** with read-level terms summed per D-10 and the learner-facing scaling of D-32. |
| R-R2 | Weights w_hit 1.0, w_lat 0.5, w_stale 3.0 (> w_hit), w_backend 1.0, w_mem 0.3, w_stampede 2.0; declared as this project's recommendation. | **DONE (tests: `test_reward_weights_match_spec_and_enforce_ordering`)**; `w_stale > w_hit` enforced. |
| R-R3 | Utilisation gate `u = 1 − max(0, util−0.9)/0.1`; stampede term outside the gate. | **DONE (tests: `test_utilisation_gate_and_stampede_outside_gate`, `test_full_cache_lowers_reward_relative_to_empty_for_the_same_outcome`)**; gate evaluated at decision time; `gate_enabled=False` ablation. See C-40. |
| R-R4 | `F_ref` = no-cache baseline for the same window/key. | **DONE (tests: `test_reward_hand_computed`, `test_utilisation_gate_and_stampede_outside_gate`)** — `F_ref = concurrent + hits` per insertion window. |
| R-R5 | Clip total to [−10, 10]; log pre-clip histogram. | **DONE with a revision (D-32)**: learner reward = `clip(raw/100, ±10)`; pre-clip `raw` is stored on every transition (test `test_reward_summary_preclip_histogram_is_recorded`, `test_scaling_clipping_and_preclip_value_preserved`); clip-fraction study in `docs/REWARD_SCALING.md`. |
| R-R6 | `w_stale` sweep {1, 2, 3, 5, 10} reported as a Pareto frontier. | NOT STARTED |
| R-R7 | Thesis wording: these terms are objective, not "shaping" (Ng et al. 1999). | **Wording decision recorded in `reward.py` docstring**; thesis text pending. |

### 3.7 Agents (R-L)

| ID | Requirement | Status |
|---|---|---|
| R-L1 | MLP 19→128→128 → dueling (V:1, A:45), ReLU, mean-subtracted advantage. | NOT STARTED |
| R-L2 | Double DQN target (online argmax, target evaluates). | NOT STARTED |
| R-L3 | AdamW lr 2.5e-4 amsgrad; Huber; grad-norm 10; batch 128; γ 0.95 (ablate 0.9, 0.99); learning_starts 10k; train every 4 decisions; Polyak τ 0.005. | NOT STARTED |
| R-L4 | numpy ring replay buffer, 200k, own seeded RNG; ablation 20k/200k/1M. | NOT STARTED |
| R-L5 | ε 1.0 → 0.1 over first 30% of training, hold 0.1. | NOT STARTED |
| R-L6 | n-step = 3 (see C-18) and PER α 0.6, β 0.4→1 — **phase 2, only after plain version learns**. | DEFERRED |
| R-L7 | ≥ 300k **decision** steps (misses, not requests). | NOT STARTED |
| R-L8 | CPU only, `torch.set_num_threads(1)`; seeds via separate processes; no vector envs. | NOT STARTED |
| R-L9 | Full seeding: PYTHONHASHSEED, random, numpy, torch, env reset, action_space, replay RNG; deterministic algorithms warn_only. | NOT STARTED |
| R-L10 | Diagnostics: TD loss, mean/max Q, target mean, ε, normalised action entropy, action histogram, per-window hit-rate variance; TensorBoard + `results.csv` with seed and commit hash. | NOT STARTED |
| R-L11 | Probe environments 1–5 pass (|err| < 0.05); hand-written DQN reaches ~500 on CartPole-v1 and matches SB3 DQN curve. | NOT STARTED |
| R-L12 | Tabular Q: 4 bins × 5 features (utilisation, hit ratio, count-1000, volatility, predicted TTL) = 1024 states × 45; state-coverage figure. | **DONE (tests: `tests/test_tabular_q.py` — Bellman update, discretiser, training determinism, no look-ahead, row validity; evidence `docs/M8_TABULAR_Q.md`)**; coverage figure `results/F_tabq_coverage.png`: 322 of 1,024 states visited with equal-frequency bins (1%), 44 with the MD-literal equal-width bins (top 10 states hold 99.7% of updates). Beats random at 1% (10/10 seeds) and ties the size-threshold rule; fails badly at 25% for γ = 0.95 (C-48). |
| R-L13 | Contextual-bandit arm = same agent with γ = 0. | **DONE for the tabular agent (`tabq:bandit`, γ = 0)**: equals γ = 0.95 at 1%, worse at 5% by 0.005 U, far better at 25% — no evidence that bootstrapping helps (C-48). The DQN version is M9. |
| R-L14 | Greedy (ε = 0) evaluation on a separate env; plus an online learning-enabled row. | **PARTIAL**: greedy (ε = 0) evaluation on separate val/test slices DONE for the tabular agent; the online learning-enabled row is NOT implemented. |
| R-L15 | numpy-only inference path from extracted weights; checkpoint includes normaliser. | NOT STARTED |

### 3.8 Baselines and bounds (R-B)

| ID | Requirement | Status |
|---|---|---|
| R-B1 | Random agent (record its number). | **DONE (test: `test_registry_is_the_frozen_list`; numbers in `results/results.csv`, `random:45`)** — OHR 0.346 ± 0.011 (1%), 0.770 ± 0.002 (25%); it beats every fixed action at 1% (C-41). |
| R-B2 | Eviction tiers via libCacheSim: Tier 0 FIFO, Random, LRU, LFU, CLOCK; Tier 1 2Q, ARC, W-TinyLFU, S3-FIFO, SIEVE; Tier 2 LeCaR (CACHEUS ideally); Tier 3 Belady (`--ignore-obj-size 1`). | NOT STARTED |
| R-B3 | TTL ladder: fixed TTL {1, 5, 30, 60, 300, 1800, ∞}; no-TTL + invalidation; statistics TTL (mean/median/p10, train split); AIMD TTL; oracle TTL (bound); global-oracle TTL (bound). | **PARTIAL (`docs/M6_BASELINES.md`)**: fixed TTL × all 3 placements × all 3 priorities (45), statistics TTL (mean/median/p10 × redis/both), AIMD (4), zero-stale oracle TTL (bound) DONE with tests `test_stat_ttl_snaps_in_log_space_and_defaults_to_3600`, `test_aimd_rules_and_bounds`, `test_zero_stale_oracle_ttl_buckets`. The ladder uses the five action buckets, not {1, 60, 300, 1800, ∞} (no ∞ action exists). NOT done: global-oracle TTL (needs a staleness budget; every fixed point is already on the frontier), no-TTL + invalidation. |
| R-B4 | Placement lattice: always-local, always-Redis, always-both (capacity-normalised), size threshold, frequency threshold k∈{2,3,5}, GDSF-style score, placement oracle (bound). | **PARTIAL (POST-HOC, Addendum M6-B)**: always-local / always-redis / always-both (fixed), hash partition (3), size threshold (3), frequency threshold (3) DONE (tests `test_hash_size_freq_placement_rules`, `test_partitioning_rules_use_both_tiers_unlike_any_fixed_action`). NOT done: GDSF-style score, placement oracle. |
| R-B5 | TTL-constrained Belady (own construction). | **DONE for unit-size objects (tests: `test_belady_matches_brute_force_optimum` — equals an exhaustive optimum on 150 random small traces for both variants, `test_bound_is_valid_for_a_real_zero_stale_policy_on_unit_size_objects`)**; byte-level bound not computed (variable-size OPT is NP-hard); reported as an OBJECT hit-ratio bound only. |
| R-B6 | Predictor-suggested-TTL arm. | **DONE (family `pred_ttl`, 2 points)** |
| R-B7 | Equal, documented tuning budget for baselines on validation; at least one offline-tuned baseline. | **DONE for the grids as frozen (docs/PREREGISTRATION.md M6-3)**: every grid point is evaluated on test and enters the frontier; per-family scalar selection uses validation only (test `test_t2_selects_on_validation_and_reports_test`). "Offline-tuned baseline the agent may not use": the whole-grid frontier plus the future-knowledge bounds. |
| R-B8 | Simple SIEVE/S3-FIFO Python implementations inside the simulator (so they can be the base eviction for arm C). | NOT STARTED |

### 3.9 Evaluation (R-E)

| ID | Requirement | Status |
|---|---|---|
| R-E1 | Chronological splits; test touched once (split boundaries: D-8). | **DONE for baselines (tests: `test_context_uses_fit_slice_only_and_equal_capacity`, `test_slices_warmup_and_row_validity`)**; the "test touched once" rule is enforced by an idempotent run_id check in `scripts/run_baselines.py` (a rerun adds 0 rows). For learned agents it is a procedure not yet exercised. |
| R-E2 | Warm-up excluded two ways (10% of test; fill cache k=1 times). | **PARTIAL**: fixed-fraction (10% of the slice) variant DONE and tested; the "cache filled k times" variant NOT implemented. |
| R-E3 | Six capacities {0.1, 0.5, 1, 5, 10, 25}% of footprint; realistic capacity nominated **in advance** as primary endpoint. | **PARTIAL**: capacities 1% (PRIMARY, pre-registered M6-1), 5% and 25% evaluated; {0.1, 0.5, 10}% not run (M11). |
| R-E4 | ≥ 3 structurally different traces + synthetic; per-trace reporting. | **NOT DONE** — one synthetic generator family only; no real trace (BLOCKED, Q-2). |
| R-E5 | 10 seeds (final); IQM + stratified bootstrap (50k aggregate / 2k pointwise) + performance profiles + probability of improvement via rliable. | NOT STARTED |
| R-E6 | Paired Wilcoxon + Holm on primary family; Cohen's d_z; absolute difference; bootstrap CI on the difference. | NOT STARTED |
| R-E7 | Metrics: OHR, BHR, stale-read rate, staleness-given-hit, staleness age mean/p95, backend per 1k reads, latency mean/p50/p95/p99/p99.9 split by hit/miss path, per-tier memory, eviction & churn, TTL histogram + MAE/signed error/over-TTL fraction vs oracle, placement shares + regret. Cumulative reward **never** in a column next to LRU. | **PARTIAL**: OHR, BHR, stale-read rate, stale|hit, stale age mean/p95, backend per 1k, latency mean/p50/p95/p99/p99.9 (overall; not split by hit/miss path), capacity evictions and TTL expirations per 1k reads, TTL median / over-TTL fraction / TTL MAE vs oracle, placement shares, action entropy DONE (`evaluation.py`). NOT done: per-tier memory, churn, placement regret, latency split by path. |
| R-E8 | Metadata bytes charged against capacity; re-run of headline (T6). | NOT STARTED |
| R-E9 | Ablations: state ladder S0–S5; joint-action arms A (joint), B (independent), C (fix-one-dim ×3), D (sequential); joint vs product-of-marginals table. | NOT STARTED |
| R-E10 | Adaptation: 4 shifts (popularity permutation, flash crowd, diurnal, write-rate ×10) with dip depth, recovery time (95%), cumulative regret, area under dip, stale spike; frozen and online variants; vs ARC, W-TinyLFU, LeCaR, AIMD. | NOT STARTED |
| R-E11 | Overhead table per policy incl. baselines; net-latency arithmetic. | NOT STARTED |
| R-E12 | Artefacts T1–T9 and F1–F11 regenerated from one `results.csv` by one command. | **T2 and F2 generated by one command (`scripts/make_f2_t2.py`; tests `test_t2_selects_on_validation_and_reports_test`, `test_frontier_and_paired_delta_and_figure`); schema DONE (tests: `test_results_round_trip`, `test_results_rejects_bad_rows`, `test_results_has_no_comparable_reward_column`)**; no generator script yet. |
| R-E13 | Threats-to-validity section naming the 12 criticisms. | NOT STARTED |
| R-E14 | Cross-trace generalisation (train A, test B) reported even if worse. | NOT STARTED |

### 3.10 Offline RL / adaptation track (R-O) — satisfies Proposal Objective 5 / FR18 (see C-27)

| ID | Requirement | Status |
|---|---|---|
| R-O1 | Logging policy = heuristic with ε = 0.15 uniform; log `action_probs` for all 45 actions. | NOT STARTED |
| R-O2 | Discrete CQL, BC, DQN on logged data (d3rlpy in a **separate venv**). | DEFERRED |
| R-O3 | OPE by WIS, DR, FQE; promote only if all agree in direction. | DEFERRED |
| R-O4 | Shadow mode, Q-value handover criterion, agreement %. | DEFERRED |
| R-O5 | Training-wheels safety condition + fallback penalty; token-bucket exploration ≤ 2%/h. | DEFERRED |
| R-O6 | Periodic retraining on era × key-group stratified buffer. | DEFERRED |

### 3.11 Live demo (R-X) — deferrable (MD Phase 8)

| ID | Requirement | Status |
|---|---|---|
| R-X1 | Compose stack: Postgres 17, Redis 8.6, lms-api (FastAPI), rl-agent, predictor-mock, Prometheus, redis-exporter, Grafana, k6 (profile). | DEFERRED |
| R-X2 | Redis config: maxmemory 128mb, allkeys-lfu, samples 10, no persistence, keyspace events `Egx`. | DEFERRED |
| R-X3 | Priority emulation Option D (ZSET + watermark reaper + LFU backstop), declared as emulation. | DEFERRED |
| R-X4 | L1 = LRUCache of (value, expires_at) honouring per-key TTL; pub/sub invalidation fan-out; cache-aside reads; write-around + invalidate. | DEFERRED |
| R-X5 | XFetch + in-process coalescing + mutex + stale fallback; `delta` stored with value. | DEFERRED |
| R-X6 | Telemetry: explicit histogram buckets; windowed rates from monotonic INFO counters; staleness sampling via `updated_at`; one Uvicorn worker for measurement. | DEFERRED |
| R-X7 | Versioned JSON contracts (inbound predictor, outbound policy, outcome), Pydantic models, schema export, conformance tests, loud major-version check. | DEFERRED |
| R-X8 | Two mirrored Redis containers for the headline live comparison; guardrails; one-`SET` rollback. | DEFERRED |
| R-X9 | Simulation-vs-deployment agreement table (T9). | DEFERRED |

### 3.12 Proposal requirements cross-check

| Proposal item | Covered by | Note |
|---|---|---|
| FR1–FR3 hit/miss/request rate received | R-F12, R-F13 | Miss rate is *received* but not fed to the network (C-26). |
| FR4–FR6 volatility, predicted TTL, hot key | R-F9, R-F10, R-F19 | Key identity replaced by hotness features (C-26). |
| FR7 unified state | R-F1–R-F20 | |
| FR8 discretised Q-learning | R-L12 | |
| FR9–FR11 DQN, replay, target net | R-L1–R-L4 | |
| FR12–FR15 joint action | R-A1–R-A4 | |
| FR16 decision to cache layer | R-X7 | Simulator applies decisions directly; contract in demo. |
| FR17 reward | R-R1–R-R5 | |
| FR18 online adaptation | R-L14 (online row), R-E10, R-O1–R-O6 | See C-27. |
| FR19 evaluation vs Q-learning, LRU, LFU | R-B1–R-B4, R-L12 | Baseline set widened; LRU/LFU kept as floors. |
| NFR1 performance overhead | R-E11, R-L15 | |
| NFR9 / Validation 7 no future info | R-P3, R-P8 | |
| Validation 4 prediction-input ablation | R-P5, R-E9 (S0–S5) | |
| Validation 5 joint-action validation | R-E9 arms A–D | |
| Validation 2 JMeter + k6 | R-X1 (k6 only) | JMeter dropped for the simulator; k6 kept for the demo (C-29). |

---

## 4. Decisions

| ID | Decision | Rationale | Status |
|---|---|---|---|
| D-1 | The MD is the authoritative final specification; the Proposal defines scope, objectives and responsibility boundaries. Where they disagree, the MD wins unless the disagreement touches an invariant (§1) or a Proposal objective, in which case it is logged in §5 and needs supervisor sign-off (Q-6). | User instruction. | ACTIVE |
| D-2 | Core simulator is a plain-Python **event-driven engine** that emits *closed* transitions; the Gymnasium class is a thin adapter for `check_env` and API hygiene only. | A Gym `step()` must return the reward for the action it was given, but in this design the reward for a decision arrives seconds-to-hours later (R-S6). Forcing it through `step()` reproduces the prototype's credit bug (C-5). | PROPOSED |
| D-3 | All torch code (DQN, probes, CartPole/SB3 check) is **written** here but **executed and tested on the user's machine** (WSL2 recommended). Nothing torch-based is marked DONE without a test log from that machine. | Torch cannot be installed in this workspace (§2). | **SUPERSEDED by D-19** |
| D-4 | Everything non-torch (trace, predictor stand-in, simulator, reward, baselines, tabular Q, analysis) is built and unit-tested here first. | It is the critical path and is testable now. | PROPOSED |
| D-5 | Build order follows §9; the first defensible result is the MVP in §8. | — | PROPOSED |
| D-6 | Canonical action encoding is the MD spec `a = p*15 + t*3 + e`; the prototype's tier-fastest order is not used (C-3). | Single source of truth; round-trip test. | ACTIVE |
| D-7 | Development seeds = 5; final reported runs = 10 seeds. | MD gives both numbers (C-15). | PROPOSED |
| D-8 | Chronological split: [0, 30%) predictor fit; [30, 70%) agent training; [70, 80%) validation (all tuning, incl. baselines); [80, 100%] test, touched once. | Reconciles the MD's two split descriptions (C-14). | PROPOSED |
| D-9 | `s'` for a closed transition = the full 19-feature observation built at the **next decision point after resolution** (whatever key). Global features are resolution-time; per-key features are that next decision's key. | The 19-vector mixes per-key and global features, so "global state at resolution time" is not a complete observation (C-16). | PROPOSED |
| D-10 | Reward aggregation per transition: read-level terms are **summed** over the reads the decision served, then the whole reward is clipped to [−10, 10]; pre-clip distribution logged. If > 5% of rewards clip, revise scaling before training (logged as a new decision). | MD leaves `hit ∈ {0,1}` undefined for a multi-read lifetime (C-19). Summing preserves "more hits is better"; the clip check prevents hot keys from saturating. | PROPOSED — needs empirical check |
| D-11 | Discounting is per decision (γ = 0.95 per closed transition). Time-based `γ^(Δt/Δt_ref)` is an ablation only, with Δt_ref = mean inter-decision time, not 1 s. | With Δt_ref = 1 s and Δt up to 7200 s the bootstrap term vanishes (C-17). | PROPOSED |
| D-12 | First DQN is 1-step. n-step and PER are added only after the 1-step agent learns. | MD says PER in phase 2; n-step over out-of-order delayed transitions is ill-defined (C-18). | PROPOSED |
| D-13 | Base eviction in the simulator is sampled-LRU (8 candidates) with priority multiplier on the eviction score; the base policy is a plug-in so SIEVE/S3-FIFO can replace it. Simulator eviction must match whatever the Redis demo uses for T9. | R-S10, C-9. | PROPOSED |
| D-14 | Capacity is in bytes; utilisation is bytes-based. | C-8. | PROPOSED |
| D-15 | Synthetic traces span hours, not seconds (e.g. ≥ 6 simulated hours), so every TTL bucket including 3600 s can expire inside the trace. | Prototype generator spans ~200 s, making TTL degenerate (C-11). | PROPOSED |
| D-16 | Synthetic predictor truth is computed from the generator's *train-split* write statistics through the same R-P1/R-P2 functions, not from the generator's hidden parameters. | Prototype hands the agent the generator's churn directly (perfect predictor by construction) (C-11). | PROPOSED |
| D-17 | Results are written only to `results/results.csv` (one row per config × seed × trace × capacity), with git commit hash and seed; all tables/figures generated from it. | MD Phase 9. | PROPOSED |
| D-19 | Torch 2.14.1+cpu is installed in the project `.venv` on the user's PC (§2b); DQN code is executed and tested there. WSL2 is not required (libcachesim, if wanted, is the only thing that would need it). | Verified by import + forward pass 2026-10-14/15. **Later blocked at import by an Application Control policy (C-47, 2026-10-15).** | **SUSPENDED (C-47)** |
| D-20 | **Staleness model (Q-3 resolved by the user's instruction "configurable staleness model")**: `StalenessConfig(mode, p_inv_l1, d_inv_l1_s, p_bypass)` with modes `lossy` (primary, option (c)), `ttl_only`, `perfect`. Default values p_inv_l1 = 0.5, d_inv_l1 = 2 s, p_bypass = 0.05 are **placeholders** and must be swept; they are not calibrated to any system. | C-6 | ACTIVE (config DONE, mechanism pending M4) |
| D-21 | A feature's as-of time is the decision request's index `i`; every window is over requests with index `< i` (request `i` itself excluded). | Gives all 19 features one interpretation; makes the leakage property checkable (`features_spec.py` docstring). | ACTIVE |
| D-22 | Default synthetic workload: 4,000 keys, 600,000 requests, 8 h, α = 0.99, write-interval median 2 h with lognormal σ = 2.0 (~19% writes). Chosen so that read-weighted time-to-next-write covers all five TTL decades (0.5% / 2% / 5% / 16% / 31% / 45% for <5 s / 5–30 / 30–120 / 120–600 / 600–3600 / >3600 s). | Prevents a single TTL bucket being trivially optimal (D-15). Values are tuning choices, not sourced. | ACTIVE |
| D-23 | Hot-key flag excludes ties at the cut-off (strictly greater than the (k+1)-th largest count). | An earlier `>=` version flagged 298/300 keys when counts tied (found by `test_hot_flag_top_one_percent_and_tie_handling`). | ACTIVE |
| D-24 | An insertion owns up to two copies (placement `both`) and CLOSES WHEN ITS LAST COPY IS GONE; `first_reason`/`first_close_time` record the first terminal event. | The MD says "first terminal event" but a decision's outcome is not realised while a copy still serves hits; closing on the first copy's eviction would drop the other copy's hits and byte-seconds from the reward. | ACTIVE |
| D-25 | Under `perfect` staleness a value that went stale during its own backend fetch is NOT inserted (insertion closed `invalidation`, zero copies). Under `lossy`/`ttl_only` it is inserted and is stale on arrival. | Otherwise `perfect` would not give stale = 0 and the gate would be untestable; the race is realistic for the other modes. | ACTIVE |
| D-26 | The decision is taken at fetch START; the value becomes visible `backend_latency` later and carries the source version at fetch start; writes do not repopulate (write-around + invalidate, as in MD Phase 8). | Needed so concurrent misses (stampede, C-20) are real misses. The MD's "write that repopulates" decision point is therefore not modelled. | ACTIVE |
| D-27 | Promotion on L2 hit is a flag, default OFF (C-36). Promoted copies inherit version and expiry, so promotion never extends an insertion's life. | Keeps `redis` and `both` distinct actions. | ACTIVE |
| D-28 | Staleness rolls (`p_bypass`, `p_inv_l1`) are pre-drawn per REQUEST INDEX from the seed (common random numbers), independent of the policy; eviction sampling uses a separate stream. | Paired comparisons across policies see the same propagation luck, lowering variance. | ACTIVE |
| D-29 | Real traces with 1-second timestamps are passed through `Trace.with_spread_timestamps()` before simulation. | Otherwise every same-second read of a key looks concurrent within an 8 ms fetch window. | ACTIVE |
| D-30 | Signal-before-learning protocol: before building or tuning an agent, quantify the value available to state-dependent rules using (i) fixed-action scans, (ii) first-half-fit / second-half-scored class rules, (iii) future-knowledge rules; label (iii) as NOT an upper bound on utility. Script: `scripts/placement_signal.py`. | Prevents attributing a flat learning curve to the DQN when the signal is simply absent (MD Phase 2 cheat-agent logic). | ACTIVE |
| D-31 | **Primary staleness regime = `harsh`** (`lossy`, p_inv_l1 0.2, d_inv_l1 10 s, p_bypass 0.3); `lossy` default and `ttl_only` are declared sensitivity arms; it is the built-in `Config()` default. Chosen by the owner 2026-10-15 AFTER the fixed-rule signal scan (disclosed in `docs/PREREGISTRATION.md`) and before any learned-agent run. | C-38, Q-8 | ACTIVE |
| D-32 | **Learner-facing reward = `clip(raw / 100, ±10)`** with D-10 summation, gate retained. Literal D-10 (`clip(raw, ±10)`) is REJECTED. | `docs/REWARD_SCALING.md`: D-10's >5% trigger fired (5.69% at 25% capacity, long TTL); literal clip was ~3 SE below the best fixed action out of sample; `div100_clip` was the best bounded candidate under the pre-declared rule. Criterion (a)'s wording admitted the unbounded `raw` vacuously; applied as intended (bounded), disclosed. | ACTIVE |
| D-33 | Per-key backend latency is simulated: `backend_us × LogNormal(mean 1, sigma 0.5)`, fixed per key from `LatencyConfig.seed`, used for the fetch window, miss latency and feature #8. `backend_sigma = 0` is the constant ablation (A-4). | Otherwise feature #8 would be a constant (dead input). | ACTIVE |
| D-34 | The simulator loop is resumable (`begin` / `next_decision` / `commit`) and `run()` is built on it; an `observer` receives every processed request. The feature tracker is fed by the observer AFTER a request and queried at the decision BEFORE the request is recorded (D-21). | Lets the trainer and the Gymnasium adapter own the control flow. | ACTIVE |
| D-35 | Rate windows use a 301-slot ring (300 completed seconds + the in-progress second). | The first version used 300 slots, which aliased the oldest second onto the current partial second; found by the brute-force cross-check. | ACTIVE |
| D-36 | **Primary capacity: L2 = 1% of unique-object footprint, L1 = 10% of L2, `harsh`**; 5% and 25% are always-reported secondaries. Named in `docs/PREREGISTRATION.md` M6-1 before any baseline ran; the value is the one proposed on 2026-10-14 (Q-7), not chosen from results. | The cost was stated in advance: at 1% TTL is nearly inert for hit ratio. | ACTIVE |
| D-37 | Baseline set frozen at 67 heuristic points + 4 bounds; nine placement-rule points (hash / size / frequency) were added post-hoc BEFORE evaluation seeds ran and are labelled `post-hoc` in `results.csv`. | A baseline set without capacity-partitioning rules would flatter a learned placement policy (C-41). | ACTIVE |
| D-38 | Frontier = non-dominated set and its concave envelope (extended flat to the right), built from seed-averaged heuristic points; bounds never enter it. The pre-registered primary statistic is the per-seed paired ΔOHR against the envelope of the OTHER heuristics. | M6-4. Note the envelope's "randomisation lies on the hull" rationale is only approximate here (C-41: mixing can lie ABOVE the hull). | ACTIVE |
| D-39 | Unit-size Belady uses capacity = (L1 + L2 bytes) / mean unique-object size; reported as an OBJECT bound only. | Variable-size OPT is NP-hard; the MD says to report `--ignore-obj-size` Belady and state that no byte bound was computed. | ACTIVE |
| D-40 | M7's secondary diagnostic uses a numpy 64-64 MLP regressor (torch blocked, C-47); decisions and criteria unchanged. | The pre-registration fixed the architecture, not the framework. | ACTIVE |
| D-41 | Tabular Q: equal-frequency (`qbin`) bins are PRIMARY, the MD-literal equal-width bins the ablation; greedy considers only actions tried ≥ 1 time in that state (Amendment M8-a) with a visit-weighted global-best fallback; 300k decisions by cold replays of the training slice. | Pre-registered before any M8 code; equal-width bins visit 44/1024 states. | ACTIVE |
| D-42 | Learned agents are never part of the baseline frontier; they are compared with it, with the placement rules and with random, paired by seed. | M6-4. | ACTIVE |
| D-18 | Proposed repository layout: `src/rlcache/{actions.py, config.py, trace/, predictor/, sim/, reward.py, agents/, baselines/, analysis/}`, `tests/`, `configs/`, `results/`, `scripts/`. Simulator and DQN do not import each other except through the transition record type. | Proposal NFR7 (separate state, training, inference, reward, adaptation). | PROPOSED |

---

## 5. Contradictions register

"Prototype" = the code blocks in the MD (verified-running only in the MD author's sandbox, at reduced dimensions; **not re-run here**). "Spec" = the MD's design specification. "Proposal" = IT23286764_PP.pdf.

### 5.1 Prototype code vs final specification

| ID | Prototype | Final spec | Resolution | Status |
|---|---|---|---|---|
| C-1 | `cache_env.py` observation has **11** features, including `is_write`, `step_i/episode_len`, and **both** hit ratio and miss ratio (`hits_l1/tot, hits_l2/tot, misses/tot` sum to 1). | 19 features; hit ratio only; no time-in-episode feature (continuing task). | Rebuild state builder to R-F1–R-F19. `step_i/episode_len` dropped (it encodes episode position in a continuing task). | RESOLVED BY SPEC |
| C-2 | `Discrete(24)` = 4 TTL × 3 prio × 2 tiers; tier 0 = "promote to L1 + L2", tier 1 = "L2 only". No local-only option. | `Discrete(45)`; placement local / Redis / both. | Implement three placements; local-only must not write to L2. | RESOLVED BY SPEC |
| C-3 | `_decode` puts tier fastest: `a = ttl*6 + prio*2 + tier`. | `a = p*15 + t*3 + e` (placement slowest, priority fastest). | D-6. | RESOLVED |
| C-4 | `step()` is called on **every request** (hits and writes included); the action is used only on miss / L2 hit. | Decide only at decision points; per-request steps dilute replay with no-op transitions. | D-2 engine with decision callback on miss/fill only. | RESOLVED BY SPEC |
| C-5 | Reward at step *i* = −log(latency of request *i*) — but request *i*'s latency is determined **before** the action is applied. The reward is therefore almost independent of the action (only the crude staleness proxy depends on it). | Delayed reward at resolution via pending transitions. | This is a credit-assignment bug in the prototype, not only a simplification. Fixed by R-S6 + D-2. | RESOLVED BY SPEC |
| C-6 | A write invalidates **both tiers instantly**, so a stale read can never happen; staleness is approximated by `volatility > 0.7 and ttl > 120` on a hit (uses the feature as ground truth). | Reward and headline claim depend on **measured** stale reads (`stale_age/ttl`), and on a hit-rate vs stale-read Pareto frontier. Spec Phase 2 still says "a write invalidates both tiers"; Phase 8 adds pub/sub fan-out to L1. | **Internal contradiction in the spec**: with perfect, instant invalidation, stale-read rate is identically 0, TTL=∞ + invalidation dominates every TTL policy, and INV-8 is untestable. A staleness mechanism must be modelled. Proposal: Redis (L2) invalidated synchronously; each **local** L1 copy is invalidated only with probability `p_inv_L1` after delay `d_inv`, otherwise it lives until TTL expiry; optionally writes bypassing invalidation with probability `p_bypass` for both tiers. Sweep these. This makes TTL × placement genuinely coupled (local copy of a volatile key = staleness risk), matching the spec's own sentence "a sidecar-only placement on a volatile key is how stale data reaches a student's results page". | **OPEN — Q-3 (blocking)** |
| C-7 | Lazy expiry only; expired entries discovered on access. | Expiry is a terminal event for pending transitions; min-heap polled every second. | Keep lazy expiry for lookups, add heap for transition closure (R-S7). | RESOLVED BY SPEC |
| C-8 | Capacity counted in entries (`len(store)`). | Utilisation = used bytes / capacity; memory term in byte-seconds. | D-14. | RESOLVED |
| C-9 | Eviction: lowest agent priority among 8 LRU-most candidates (priority dominates recency absolutely). | Priority = multiplier on eviction score; base policy pluggable; demo uses ZSET reaper + LFU. | D-13; multiplier values A-6. | PARTLY OPEN (A-6) |
| C-10 | `reset()` clears both caches and samples a random 512/2048-request window anywhere in the trace. | Continuing task; warm cache; chronological split (train only on its slice). | No per-window reset of cache state; reporting windows are cuts in a continuous run; training samples only within the training slice. | RESOLVED BY SPEC |
| C-11 | `make_synthetic_trace`: exponential(0.001) gaps → 200k requests span ~200 s, so 600/3600 s TTLs never expire; `pred_ttl = 60/(vol+0.05)` derived from the generator's hidden churn (perfect predictor); no temporal locality; `zipf % n_keys` folds the tail. | TTL must matter; predictor must be fit on the past; locality; truncated Zipf. | D-15, D-16, R-D7. | RESOLVED |
| C-12 | `self.recency`, `self.freq` grow without bound. | Bounded state; per-key metadata charged against capacity. | R-S16; metadata accounting R-E8. | RESOLVED BY SPEC |
| C-13 | `train.py` counts `TOTAL_STEPS` in env steps (= requests) and stores each step immediately in replay; 1-step; Polyak update only on training steps. | ≥ 300k **decision** steps; transitions enter replay on closure; τ every step (spec table) vs every train step (code). | Count decisions; push on closure; apply Polyak after each gradient step (code behaviour) and record it — the spec's "every step" with no gradient in between is a no-op difference only in rate. | RESOLVED (D-12) |
| C-14 | Two split descriptions: 60/20/20 and 30/50/20. | — | D-8. | RESOLVED |
| C-15 | Phase 5 success criterion: 5 seeds; Evaluation: 10 seeds. | — | D-7. | RESOLVED |
| C-16 | — | "`s'` = global state at resolution time", but the state is 19-dim with 10 per-key features. | D-9. | RESOLVED (proposed) |
| C-17 | — | γ = 0.95 justified as a ~20-decision horizon, yet also `γ_eff = γ^(Δt/1 s)` with Δt up to 7200 s (γ_eff ≈ 0). | D-11. | RESOLVED (proposed) |
| C-18 | — | n-step = 3 alongside delayed, out-of-order transition closure (no single ordered trajectory). | D-12; if n-step is added, order transitions by closure time and state that definition. | RESOLVED (proposed) |
| C-19 | — | Reward formula uses `hit ∈ {0,1}` and per-request `L`, but one transition spans many reads. | D-10. | RESOLVED (proposed, needs check) |
| C-20 | — | Stampede term and feature #18 assume concurrency; the trace has 1-second resolution and the simulator is sequential. | Define concurrency as: misses on the same key whose backend fetch windows overlap (fetch occupies `[t, t + backend_latency]`); in-flight = number of open fetch windows. Assumption A-5. | RESOLVED (proposed) |
| C-21 | Tabular Q `FEAT_IDX = [10, 11, 4, 0, 8]` with comment "utilisation, hit ratio, freq, volatility, pred TTL". | In the 19-vector (0-based) volatility is index **9**; index 0 is log recency. | Use `[10, 11, 4, 9, 8]`; add a test that maps names to indices. | RESOLVED |
| C-22 | Replay-buffer docstring sized for obs_dim 11. | 19 dims, 200k. | Cosmetic; buffer is dimension-generic. | RESOLVED |

### 5.2 Inside the spec: simulation vs live demo

| ID | Conflict | Resolution | Status |
|---|---|---|---|
| C-23 | Demo TTL buckets: "drop 3600, use first four" (→ {5,30,120,600}, 36 actions) **and** "top out around 300 s"; contract example uses `ttl_seconds: 45`, `T_45`, priority 0–10 (`9`). All violate INV-2/INV-5/INV-6. | Demo must use the same 45-action space and the same bucket values, or the deployed policy is not the trained policy. Recommend keeping {5,30,120,600,3600} and the 3 priority levels in the contract; demo credit window = 2×max bucket. | **OPEN — Q-4** |
| C-24 | Demo decides per **key-group every 30 s** (72 groups, aggregate state, per-window reward); simulator decides per **key on miss** with per-key state and per-decision reward. Different MDPs: a policy trained in simulation cannot be deployed unchanged. | Recommend: demo also decides per key on miss, using the **in-process numpy forward pass** (measured 13.6–15.4 µs in MD; needs re-measuring) inside `lms-api`; the `rl-agent` container keeps training/telemetry/shadow logging. This preserves one MDP and the research idea; the MD's argument for out-of-band was the HTTP hop, which in-process inference removes. Key-group mode becomes an optional engineering variant. | **OPEN — Q-4** |
| C-25 | `guardrails.py` reward (window-level hit ratio − p99 − DB qps − mem − stale − fallback) differs from R-R1. | Use R-R1 per decision everywhere; fallback penalty added as a separate term only in canary mode. | PROPOSED |

### 5.3 Proposal vs final specification

| ID | Proposal | Final spec | Resolution | Status |
|---|---|---|---|---|
| C-26 | State = hit rate, **miss rate**, request rate, volatility, predicted TTL, **cache key** (6 inputs). | 19 features; no miss rate (redundant); no key identity (does not generalise). | Follow spec (INV-1); thesis explains the change. FR2/FR6 inputs are still *received*. | Needs supervisor note (Q-6) |
| C-27 | Objective 5 / FR18: "continuous online retraining against live traffic". | Offline RL + OPE + shadow + canary + **periodic** retraining; online learning evaluated in the simulator. | Objective 5 kept, implemented as (a) online learning-enabled variant in the simulator with injected shifts (R-L14, R-E10) and (b) periodic retraining track (R-O). Wording change needs sign-off. | Needs supervisor note (Q-6) |
| C-28 | Experiments "within the campus LMS environment" on system telemetry. | Primary results on public Twitter trace + synthetic in simulation; LMS only in the deferrable demo. | Follow spec; LMS demo supplies the "real system" evidence. | Needs supervisor note (Q-6) |
| C-29 | Tools: TensorFlow, Kubernetes, JMeter + k6, Kafka. | PyTorch; Docker Compose (no K8s); k6 only. | Follow spec for this component. Kafka is Component 4's concern. | Needs supervisor note (Q-6) |
| C-30 | Baselines: Q-learning, LRU, LFU. | Adds Tier-1 eviction policies, TTL ladder, placement lattice, bounds. | Additive — compatible. | RESOLVED |
| C-31 | WBS ends Oct 2026 (Evaluation Oct W2–W3, Docs Oct W3–W4); Gantt runs component work to 31 Dec 2026. Today is 14 Oct (WBS week of "Evaluation"). | Phases 0–5 = October deliverable if the boundary is October. | Q-5. | OPEN |
| C-33 | — (MD Phase 1 `synthetic_predictor` docstring) | Claims interpolating truth with a shuffled copy keeps "the marginal distribution identical at every accuracy level". | **False** for `a*true + (1-a)*shuffled`: variance shrinks by `a² + (1-a)²` (test `test_interpolate_mode_shrinks_variance_contradicting_md_claim`). Default replaced by element-wise `mixture`, which preserves the marginal. The MD's literal version is kept as `mode="interpolate"`. | RESOLVED |
| C-34 | — | MD Phase 0 expects `ftp://…/twemcacheWorkload/open_source/` to list shards. | Directory is a dangling symlink on CMU's side (`docs/DATA_ACCESS.md`). Not a local problem. | OPEN (Q-2) |
| C-35 | — | MD "Data" recommends cluster12/52 as multi-hour training/eval traces; the repo `samples/` fallback it lists in the risk register provides only 1M-row, 1–9 minute slices. | Samples validate the parser only; they cannot support TTL-expiry or volatility experiments. | OPEN (Q-2) |
| C-36 | — (R-S2, MD Phase 2 semantics) | "Promotion into L1 on an L2 hit" together with a placement action {local, redis, both}. | With promotion always on, a `redis` decision becomes `both` after the first re-read, so INV-7's placement dimension collapses. Promotion is a config flag, default OFF (D-27); test `test_promotion_flag_controls_placement_collapse` shows the collapse. | RESOLVED (by flag) |
| C-37 | — (MD reward table) | `L0` = p50 backend latency so `exp(−L/L0)` is ≈ 0.37 on a miss and ≈ 1.0 on a local hit; placement meant to trade latency against capacity and duplication. | `exp(−L/L0)` = 0.9999 (L1), 0.9632 (L2), 0.3679 (backend): L1 over L2 is worth `w_lat·0.037 = 0.018` per hit vs a staleness cost up to 3.0. In the simulator `both` is Pareto-dominated by `redis` (25% capacity, lossy: stale 9.1% vs 2.2% for +0.2 pp OHR) and `local` is capacity-starved (`docs/M4_SIM_DIAGNOSTIC.md`). The placement dimension may carry little learnable signal. | **INVESTIGATED 2026-10-15 (`docs/PLACEMENT_SIGNAL.md`)**: placement signal exists but is small (≈ 0.000…+0.009 U/read even with future knowledge; out of sample ≤ +0.0024 on top of per-class TTL); `local` is dominated everywhere; `both` ≈ `redis`. The learnable choice is effectively `redis` vs `both`. See C-38 for why TTL signal is the real yardstick. Placement stays in the action space (INV-2/INV-7); expect "gains concentrate in TTL". |
| C-38 | C-6 (staleness model) | The MD's headline is a (hit ratio, stale-read) Pareto frontier from joint TTL + placement, while its write path is "write-around + invalidate". | Measured in `docs/PLACEMENT_SIGNAL.md`: when invalidation is reliable (the default `lossy` model, L2 synchronous) per-class TTL adds only +0.001…+0.004 U/read, because a long TTL is nearly free; with unreliable invalidation (`harsh`) +0.027, with none (`ttl_only`) +0.064 (per key +0.087). The research question is only non-trivial when staleness has teeth, so the primary staleness regime must be **chosen and pre-registered before any learned-agent run**, with the others reported as sensitivity — not picked after seeing which one favours the agent. | **OPEN — Q-8** |
| C-39 | — (MD reward table) | `w_mem · bytes_held·seconds_held / (capacity · T_window)` is presented as a term that charges memory use. | With `capacity` = total cache bytes and `T_window` = 3600 s, one decision's term is ~10⁻⁴ of its hit term: mean contribution < 0.0001 (`docs/REWARD_SCALING.md`). The memory objective is inert as specified; a `w_mem` sweep would be meaningless. A different normalisation (e.g. per-decision mean byte-seconds) is a design choice for the owner. | **OPEN** |
| C-40 | — (R-R3, MD correction six) | A utilisation gate `u = 1 − (util − 0.9)/0.1` that "collapses reward only as the cache approaches full". | In a capacity-constrained cache with eviction the cache is full in steady state: 97.7% of decisions under a long-TTL policy were taken at utilisation > 0.9, and `u` reaches 0 at a full cache. Measured effect on action ranking is nil (removing it moved alignment by < 1 SE), so R-R3 is kept and `gate_enabled=False` is an ablation arm. | OPEN (conceptual); no action needed for correctness |
| C-41 | C-37 (this REVISES it) | C-37 concluded placement carries little signal (tested at 25% capacity with class-level rules). | At the primary 1% capacity `random:45` beats all 45 fixed actions (OHR 0.346 vs 0.332, +1.39 pp, 10/10 seeds); diagnosis: random over placements alone 0.344, over TTL alone 0.325, over priority alone 0.335. Mixing `local` and `redis` uses L1 and L2 as DISJOINT capacity, which no fixed action can. Deliberate partitioning (`place_size:p25`) reaches 0.363 (+3.07 pp, se 0.32, 10/10) at +0.34 pp stale. So placement has real value at small capacity — as capacity partitioning, not as latency/staleness trade-off; at 25% it is small, as C-37 found. | RESOLVED (finding); the learned agent must be compared with these rules, not with `fixed:redis` |
| C-42 | — | The baselines' predicted/statistic TTLs approximate "TTL = time to next write". | At 25% the zero-stale oracle TTL reaches OHR 0.803 at 0.02% stale; the best baseline with comparable staleness (`fixed:redis/30s`) has 0.50 at 0.2% (+30.3 pp, se 0.16, 10/10) and the best predictor-based baseline (`stat_ttl:p10`) 0.79 at 2.3% stale. The headroom is on the stale axis and is information-limited (statistics fitted on the first 30% of the trace). | OPEN — this is what an agent with write-recency features could capture |
| C-43 | — | M6 gate: "oracle-TTL has zero stale reads". | Not literally true: 0.01–0.02% (redis), 0.05% (both). A key rewritten within 5 s still receives the 5 s minimum bucket, and the copy outlives the fetch by up to the fetch latency. Documented in `docs/M6_BASELINES.md`; the bound is labelled "near zero". | RESOLVED (documented) |
| C-44 | — | Stale-read rates are summarised by their mean. | Between-seed sd is as large as the mean (fixed redis/3600 at 1%: 0.00–1.37% across seeds; 5%: 0.21–10.7%). The seed-averaged frontier hides this; comparisons must be paired by seed (the pre-registered statistic is). | RESOLVED (procedure) |
| C-45 | M7 Addendum (pre-registered) | A predictor-driven statistic TTL should lower stale reads vs an uninformative predictor. | Holds at 5% and 25% (stale 2.86 → 1.34%, 5.97 → 3.01%; monotone, Spearman −1.0, 9/10 and 10/10 seeds, no hit-ratio cost). **Fails G1 at the primary 1%** (0.012 pp, CI straddles 0). Pre-registered outcome: PARTIAL — the primary endpoint carries no usable TTL-prediction signal; the TTL claim rests on the 5%/25% arms. | RESOLVED (finding); binding on the write-up |
| C-46 | — | The 19 features give the agent "enough" to choose TTL. | Held-out R² of the observation for the ideal-TTL target is 0.44–0.52 with the predictor features and 0.006–0.126 without them (3 dev seeds, 1% and 25%). The history/cache features carry almost no information about time-to-next-write; there is no "time since last WRITE" feature. The agent's TTL ability is therefore capped by the frozen fit-once predictor. | OPEN (design observation; INV-1 fixes the features) |
| C-47 | D-19 | "Torch runs on this machine." | **PyTorch is blocked** by a Windows Application Control policy: `WinError 4551` loading `torch_python.dll`, reproducible; it worked at install time (2026-10-14). I did not try to bypass it (that would change a security setting). Consequence: **M9 (DQN, probes, SB3 CartPole check) cannot run on this machine as is.** M7/M8 are unaffected (numpy only). | **OPEN — needs the owner** (allow the DLL under the policy, or run torch elsewhere, e.g. WSL2/another machine) |
| C-48 | MD Phase 4 ("tabular Q should plausibly match a fixed-TTL heuristic") | A bootstrapped value learner is the method under study. | With γ = 0.95 the tabular agent collapses at 25% capacity in 6 of 10 dev seeds (U 0.57–0.84 vs ≈1.2; OHR 0.55 vs 0.76 for random) and on the evaluation seeds (ΔU −0.19 vs random, −17.7 pp OHR; 4/10 seeds better). γ = 0 does not collapse and is better at 25% (+0.080 vs random, 10/10). Hypothesis (not controlled): the continuation `γ·max Q(s')` is nearly action-independent because s' is the NEXT DECISION of an arbitrary key (D-9), so it injects noise that swamps the action-dependent reward; Q-values are ~20× larger than the bandit's. A neural agent faces the same structure. | **OPEN** — any fix needs a new addendum and fresh dev seeds 110–119 |
| C-49 | M6-4 (primary statistic) | ΔOHR vs the concave envelope measures "beating the frontier". | The envelope is extended FLAT to the right, so a policy with more staleness than every baseline can show ΔOHR > 0 without dominating anything (tabq:qbin at 1%: +0.67 pp ΔOHR but +0.17 pp stale vs `place_size:p25`; tie on U). ΔOHR must always be reported with the stale delta and a two-axis dominance check; INV-8 needs dominance, not ΔOHR. | RESOLVED (reporting rule) |
| C-50 | M6-2 (capacity from whole-trace footprint) | Capacity is a design parameter, not information. | It is computed from the footprint (unique-object bytes) of the WHOLE trace, so cache size carries a little knowledge of the future key set. Scrambling post-training keys changes capacity and therefore the learned table; with capacity held fixed training is bit-identical (`test_training_uses_only_the_training_slice`). Mild, applies equally to all policies, stated for the write-up. | RESOLVED (documented) |
| C-32 | Responsibility table: volatility-score generation listed under "Other member — Nirmal", LSTM/ARIMA under Kumod. | Spec builds its own volatility/predicted-TTL stand-in. | Stand-in is a **test fixture and ablation instrument**, not a replacement for the teammates' component; interface frozen by contract (R-X7, R-P6). | RESOLVED |

---

## 6. Assumptions (must be stated in the thesis)

| ID | Assumption | Validation plan |
|---|---|---|
| A-1 | Trace "writes" are source-of-truth mutations behind the cache (DB writes), not cache `set`s of the new value. | State explicitly; it is what makes invalidation and staleness meaningful. |
| A-2 | Staleness parameters (`p_inv_L1`, `d_inv`, `p_bypass`) per Q-3. | Sensitivity sweep. |
| A-3 | Backend latency 8 ms is unsourced. | Sweep {1, 8, 50} ms (R-S15). |
| A-4 | Per-key backend fetch latency (feature #8) is not in any trace: modelled as per-key lognormal around the backend mean, fixed per key. | Ablate (feature constant vs varying). |
| A-5 | Concurrency for stampede/in-flight is defined by overlapping fetch windows (C-20). | State; check that the term is nonzero on hot keys. |
| A-6 | Priority multipliers on the eviction score: low ×0.5, normal ×1, high ×2 (score = "keep value"; lowest evicted). | Placeholder; tune on validation and log. |
| A-7 | L1 = one sidecar per Twitter `client_id` (frontend service) is **considered** as a way to model multiple sidecars; default for the MVP is a single L1. | Decide after Q-3. |
| A-8 | Hard cap for an open transition = 7200 s (2 × 3600). | — |
| A-9 | Volatility and predicted-TTL formulas, three-way read classification, TTL-constrained Belady, placement lattice, TTL ladder, reward weights, normalisation, adaptation metrics are this project's own constructions. | Never cite as prior work. |
| A-10 | Max values for log-normalisation (Δt_max, size max, latency max, rate max) are fit on the training split and frozen. | Leakage test R-P8. |
| A-11 | `hot_key_flag` truth = key in top-1% of training-split request counts (stand-in rule). | State; replaced by the teammate's flag later. |
| A-12 | User's machine can run WSL2 with Ubuntu ≥ 22.04 (glibc ≥ 2.35) for libcachesim and torch. | Confirm (Q-1). |

---

## 7. Open questions (need the user / supervisor)

| ID | Question | Blocking? | Recommended answer |
|---|---|---|---|
| Q-1 | Is there an existing project folder on your PC with prototype code? If so, connect it ("+" → Add folder) so it can be inspected. Can you run WSL2? | Blocks C-section completeness for any *local* code | — |
| Q-2 | Can you list/download the Twitter plain-text trace from your own connection (CMU FTP or SNIA IOTTA)? | Blocks real-trace results, not the MVP | **Answered partly 2026-10-15**: CMU FTP path is dangling; SNIA needs a browser (JS challenge + licence); repo samples obtained but too short. **Still needed:** fetch cluster12 / cluster52 `.zst` parts from SNIA IOTTA type 17 yourself, place under `data/raw/twitter_full/` (`docs/DATA_ACCESS.md`). |
| Q-3 | Staleness model (C-6). Choose: (a) L1 invalidation is lossy/delayed (`p_inv_L1`, `d_inv`), Redis synchronous; (b) both tiers TTL-only (no invalidation) as the primary setting; (c) (a) + a small `p_bypass` for writes that skip invalidation. | **Yes — the reward and headline claim are undefined without it** | (c), with (b) and "perfect invalidation" as sensitivity endpoints. **RESOLVED 2026-10-15 by D-20** (user asked for a configurable model; all three modes are config options; values are placeholders). |
| Q-4 | Demo cadence and action space (C-23, C-24). | Only for Phase 8 | Per-key on miss, in-process numpy inference, identical 45 actions. |
| Q-5 | What is the actual deliverable for the October boundary vs the 2027 completion? | Scheduling | MVP (§8) as the October/progress deliverable. |
| Q-6 | Supervisor sign-off on C-26–C-29 (proposal deviations). | Thesis wording | Short memo listing the four changes with one-line justification each. |
| Q-7 | Name the "realistic" capacity (primary endpoint) before any training run. | Before first experiment | 1% of footprint for L2, L1 = 10% of L2. **RESOLVED 2026-10-15 by D-36.** |
| Q-8 | ~~**Which staleness regime is primary?** `lossy` default (reliable L2 invalidation; TTL nearly irrelevant, C-38), `harsh` (p_inv 0.2, d 10 s, p_bypass 0.3), or `ttl_only`. Needs a fact about the real LMS/Redis: how reliable is invalidation (other writers, missed pub/sub, cache-aside races)? Also: should L1 be modelled as one sidecar per service instance (A-7), which could change the placement finding? | **Yes — before any learned-agent run** | Pre-register `harsh` as primary and report `lossy` and `ttl_only` as declared sensitivity arms; decide the sidecar question with the supervisor. |~~ **RESOLVED 2026-10-15 by D-31** (regime). The per-service-sidecar modelling question (A-7) and the real LMS invalidation reliability remain open for the supervisor. |

---

## 8. Smallest experimentally defensible implementation (MVP)

**Claim it can support:** "On a held-out chronological test split of a synthetic workload with per-key write rates (and Twitter cluster12 if R-D1 succeeds), at one pre-registered capacity and a fixed base eviction policy, a Double Dueling DQN over the 19-feature / 45-action / multi-objective formulation does / does not reach a (hit ratio, stale-read rate) point outside the frontier traced by fixed-TTL × {always-Redis, always-both, always-local} policies, over 5 seeds." Either outcome is reportable.

**Contains (all invariants present, nothing reduced):**
1. `actions.py` — 45-action codec + round-trip test.
2. Synthetic trace generator (D-15, R-D7 minus shift injectors) + chronological split (D-8) + oracle `next_write` annotation.
3. Predictor stand-in fit on [0, 30%) (R-P1, R-P2, R-P4, A-11) + leakage test.
4. Event-driven simulator: two tiers, bytes, lazy expiry + heap, sampled-LRU with priority multiplier, staleness model per Q-3, fresh/stale/miss accounting, pending transitions, 19-feature state + frozen normaliser, R-R1 reward with D-10 aggregation.
5. Non-learned policies on the same engine: random, fixed-TTL ladder × 3 placements, statistics TTL, oracle TTL (bound).
6. **Signal test without any DQN**: statistics-TTL policy driven by `synthetic_predictor(1.0)` vs `(0.0)` must differ in stale-read rate. If it does not, the features carry no signal and DQN work stops until fixed.
7. DQN (1-step Double Dueling) + probes 1–5 + CartPole-vs-SB3 check — **run on the user's machine**.
8. γ = 0 bandit arm and tabular Q (both nearly free once 4 and 7 exist).
9. `results.csv` + one script producing F2 (Pareto) and T2 at the one capacity.

**Explicitly not in the MVP:** libCacheSim eviction suite, PER, n-step, capacity sweep, multiple traces, shift experiments, rliable statistics beyond median/IQR, offline RL, Redis demo. Each is additive on top of the MVP without changing its interfaces.

**Why it is defensible:** it compares against the baseline the headline claim actually needs (the fixed-TTL frontier at equal capacity and eviction), uses a held-out chronological test split with a frozen predictor, has a no-DQN signal check and probe-validated learner, reports seeds, and claims no more than one capacity on one or two traces.

---

## 9. Dependency-ordered implementation plan

Each milestone has a gate; the next milestone does not start until the gate passes and is logged in §10.

| M | Build | Depends on | Gate (must be a run test) | Where it runs |
|---|---|---|---|---|
| M0 | Repo skeleton, pinned `requirements*.txt` (main venv; separate `offline` venv for d3rlpy later), `pytest` config, `results.csv` schema, config dataclasses with all constants from §3. | — | `pytest` collects; config loads. | here |
| M1 | `actions.py`, reward-weights config, feature-name ↔ index table. | M0 | Round-trip over 45 actions; index-name test (catches C-21). | here |
| M2 | Synthetic generator, chronological splitter, oracle annotator (`next_access`, `next_write`), Twitter streaming parser (tested on a hand-written 20-line fixture until real data exists). | M0 | Generator: per-key write-rate spread > threshold; span ≥ 6 h; parser handles all 11 ops and non-`:` delimiters; oracle passes brute-force check on small trace. | here |
| M3 | Predictor stand-in + synthetic accuracy knob + leakage test. | M2 | Fit only sees [0,30%); accuracy=1 equals truth; accuracy=0 is permutation (same marginal). | here |
| M4 | Simulator engine: tiers, expiry heap, eviction w/ priority, staleness model, invalidation, accounting. **No RL yet.** | M1, M2, **Q-3** | Invariants: every insert closed exactly once; counts fresh+stale+miss = reads; with perfect invalidation stale = 0; byte usage ≤ capacity; deterministic under seed. | here — **GATE PASSED 2026-10-15** (`tests/test_simulator.py`, 41 tests; full suite 128 passed) |
| M5 | Feature tracker (bounded), normaliser, pending-transition manager, reward computer, decision-callback API, Gymnasium adapter. | M3, M4 | Each feature unit-tested on toy traces with hand-computed values; reward sign tests (stale read lowers r; over-full lowers r); pre-clip reward histogram on random policy; `check_env` passes. | here — **GATE PASSED 2026-10-15** (`tests/test_features.py` 15, `tests/test_reward_transitions_env.py` 15; full suite 161 passed). Pre-clip histogram: `docs/REWARD_SCALING.md` |
| M6 | Non-learned policies + evaluation runner + `results.csv` writer + F2/T2 script. | M5 | Random-policy and fixed-TTL ladder numbers recorded; oracle-TTL has zero stale reads and is never beaten on hit ratio by a zero-stale policy. | here — **GATE PASSED 2026-10-15 with one literal miss**: fixed-ladder and random numbers recorded; oracle-TTL stale is 0.01–0.05%, not exactly 0 (C-43); full suite green. Evidence `docs/M6_BASELINES.md` |
| M7 | Signal test (MVP item 6). | M6 | Stale-read rate differs between accuracy 1.0 and 0.0 beyond seed noise. **If not → back to M3/M5.** | here — **RUN 2026-10-15, outcome PARTIAL** (pre-registered rule): criteria fail at the primary 1% (G1: CI [−0.006, +0.033] pp), pass at 5% and 25%; secondary regression supportive. `docs/M7_SIGNAL_TEST.md` |
| M8 | Tabular Q (D-fixed indices) + coverage figure. | M5 | Beats random on validation. | here — **GATE PASSED 2026-10-15 (pre-registered rule, dev seeds 100–109)**: ΔU vs random +0.0179 [+0.0141, +0.0218] 10/10 at 1%, +0.0131 at 5%, **−0.243 at 25% (fails)**; evaluation seeds confirm. `docs/M8_TABULAR_Q.md` |
| M9 | DQN modules (net, numpy replay, ε schedule, Double target, Polyak), probes 1–5, CartPole + SB3 comparison script, training driver over closed transitions, γ=0 switch. | M5 | Probes within 0.05; CartPole ~500; matches SB3. **Run by user; logs pasted back.** | user machine **— BLOCKED 2026-10-15 by C-47 (torch cannot be imported here).** |
| M10 | MVP experiment: 5 seeds, one capacity (Q-7), synthetic (+ cluster12 if R-D1 passed). | M6–M9 | F2 + T2 produced from `results.csv`; action-entropy not collapsed (or collapse reported). | user machine |
| M11 | Extensions in order: libCacheSim baseline suite & Belady; SIEVE/S3-FIFO base eviction; capacity sweep; second/third trace; w_stale sweep; predictor ablation; state ladder; joint-action arms A–D; shift experiments; PER & n-step; rliable statistics; overhead table. | M10 | Per-item. | both |
| M12 | Offline-RL / OPE track (separate venv). | M10 | — | user machine |
| M13 | Redis demo (deferrable, after Q-4). | M10 | Sim-vs-deployment agreement. | user machine / here for smoke tests |
| M14 | Write-up artefacts T1–T9, F1–F11 from one command. | all | Regenerates cleanly. | both |

---

## 10. Change log

| Date | Entry |
|---|---|
| 2026-10-14 | File created. Both sources read. Environment probed (§2). No code written. Plan presented to user; awaiting answers to Q-1, Q-3 (blocking for M4), Q-5, Q-7 and go-ahead. |
| 2026-10-15 | **M0, M1, M2, M3 implemented and gated.** Files: `pyproject.toml`, `requirements.txt`, `requirements-offline.txt`, `configs/default.yaml`, `src/rlcache/{config,actions,features_spec,results_schema}.py`, `src/rlcache/trace/{record,parser,synthetic,splits,oracle}.py`, `src/rlcache/predictor/standin.py`, `scripts/profile_trace.py`, `tests/{test_actions,test_config_and_schema,test_trace_parser,test_synthetic_split_oracle,test_predictor}.py`, `tests/fixtures/twitter_mini.csv`, `docs/DATA_ACCESS.md`. `pytest`: **87 passed**. Failures found and fixed along the way: (i) hot-key flag flagged tied keys (code bug, D-23); (ii) seven failing tests on first run, all errors in MY test expectations rather than the code (miscounted fixture keys and rows in three tests, a bad-row limit too tight for 3/2003 rows, a locality metric insensitive under Zipf, an absolute flash-crowd bound ignoring the Zipf baseline, an over-write-heavy oracle fixture). Real Twitter samples obtained (R-D1 schema proven) but unusable for TTL/volatility experiments (C-35). Torch installed (D-19). Next: M4 simulator. |
| 2026-10-15 | **M4 implemented and gated.** New: `src/rlcache/sim/{engine,policy}.py`, `tests/test_simulator.py` (41 tests), `scripts/sim_grid.py`, `docs/M4_SIM_DIAGNOSTIC.md`; `CacheConfig` gained `l2_footprint_frac`, `promote_on_l2_hit`, `hard_cap_s`; `Trace.with_spread_timestamps()`. `pytest`: **128 passed**. Found while testing: (i) first run had 11 errors + 3 failures, all in my fixtures/expectations (write-volume guard rightly refused an over-written fixture; three tests ended before the last fetch materialised); (ii) one real engine gap, a write racing its own fetch left a stale value under `perfect` invalidation (D-25). Simulator diagnostics (synthetic, one seed): OHR 0.34→0.83 and stale 0→2.2% across the TTL ladder at 25% capacity; `both` dominated by `redis`; placement signal weak (C-37, OPEN). Next: M5 (feature tracker, normaliser, reward, pending-transition manager, Gymnasium adapter). |
| 2026-10-15 | **C-37 investigated** before M5 (user request). New: `scripts/placement_signal.py`, `docs/PLACEMENT_SIGNAL.md`; `Regime`-level sweeps over capacity, tier ratio, staleness, `L0`, Zipf α. Result: `local` dominated everywhere; `both` ≈ `redis` under spec constants; volatility-aware placement worth ≤ +0.009 U/read with future knowledge and ≤ +0.0024 out of sample; per-key placement overfits (negative). Larger finding (C-38): TTL signal itself depends on invalidation reliability (+0.001…+0.004 reliable → +0.064…+0.087 `ttl_only`), so the primary staleness regime is a pre-registration decision (Q-8). My first "oracle TTL" was mislabelled as a bound — it is a zero-stale rule and often scores below the best fixed TTL; relabelled. Caveats: 3 workload seeds, synthetic only, single sidecar. No simulator code changed; 128 tests still pass. |
| 2026-10-15 | **M5 implemented and gated; primary staleness regime pre-registered (D-31).** New: `src/rlcache/{features,reward,transitions,runner,env}.py`; engine gained per-key backend latency, a resumable `begin/next_decision/commit` loop and an observer hook (`tests/test_simulator.py` +3 tests, 3 white-box tests rewritten); `tests/{test_features,test_reward_transitions_env}.py`; `scripts/reward_scaling.py`; `docs/{PREREGISTRATION,REWARD_SCALING}.md`. `pytest`: **161 passed**; mutation checks on window, gate and `s'` were all caught. Found: (i) rate-window aliasing bug (300-slot ring) caught only by the full-trace brute-force cross-check (D-35); (ii) D-10 literal clipping rejected (D-32); (iii) memory term inert (C-39); (iv) gate pinned near 0 in steady state but with no measurable ranking effect (C-40); (v) 1% of decisions carry 73–84% of total reward; (vi) class-level agents gain at most ~+0.006 U/read over the best fixed action, so expect small learned-agent margins. A post-hoc gate-off arm was added after seeing results and is labelled as such (Addendum A). Next: M6 (non-learned baselines, evaluation runner, results.csv writer, F2/T2 script). |
| 2026-10-15 | **M6 implemented, pre-registered and run.** Pre-registration (primary capacity 1%, protocol, frozen baseline list, frontier statistic) was written BEFORE any M6 code ran. New: `src/rlcache/{evaluation.py,baselines/{policies,bounds}.py,analysis/{pareto,report}.py}`, `scripts/{run_baselines,make_f2_t2}.py`, `tests/test_baselines_eval.py` (26 tests), `docs/M6_BASELINES.md`; engine `Metrics` gained measured-window utility counters; results schema gained `family`, `utility`. Brute-force check: the Belady bounds equal an exhaustive optimum on 150 small random traces; mutation checks caught a dropped warm-up exclusion, bounds leaking into the frontier, and writes not evicting in the TTL-constrained bound (one mutation was an equivalent mutant, not a test gap). A development run (seed 100) showed `random:45` beating all fixed actions; diagnosis attributed it to placement partitioning; nine placement-rule baselines were added post-hoc BEFORE evaluation seeds ran, disclosed in Addendum M6-B and labelled in the data. One-time evaluation run: 71 policies × 2 splits × 3 capacities × seeds 0–9 = 4,260 rows (740 s). Findings C-41 (revises C-37), C-42, C-43, C-44. A shell-escaping slip twice left a literal newline inside a string in `report.py`/a doc patch and was fixed; no result was affected. Next: M7 (signal test: statistics-TTL driven by predictor accuracy 1.0 vs 0.0 must differ in stale-read rate) then M8 (tabular Q). |
| 2026-10-15 | **M7 run, outcome PARTIAL.** Pass criterion and decision rule pre-registered before any M7 code existed. New: `src/rlcache/analysis/signal.py`, `scripts/signal_test.py`, `tests/test_signal.py` (12 tests), `docs/M7_SIGNAL_TEST.md`. Dev seeds 100–109 only. Result: G1–G4 fail at 1% (G1), pass at 5% and 25% with monotone dose-response; secondary regression supportive but shows the non-predictor features carry almost no TTL information (C-45, C-46). **Environment break found while testing:** `import torch` now fails with WinError 4551 (Application Control policy); not bypassed; M9 blocked (C-47); the M7 diagnostic MLP was rewritten in numpy (D-40). |
| 2026-10-15 | **M8 implemented, gated and run.** Pre-registered (criterion, protocol, Amendment M8-a) before any agent code. New: `src/rlcache/agents/tabular_q.py`, `scripts/{tabq_gate,run_tabular_q,tabq_coverage}.py`, `tests/test_tabular_q.py` (13 tests), `docs/M8_TABULAR_Q.md`; report module gained learned rows, `learned_vs_baselines`, gold-star markers in F2. Dev gate (seeds 100–109, val): PASS at 1% and 5%, FAIL at 25% (C-48); evaluation seeds 0–9 run ONCE (180 rows, 1,615 s) with the unchanged configuration. A test that appeared to show look-ahead was a capacity artefact (C-50); fixed in the test, not in the code. No hyper-parameter was changed after reading the gate. Totals: 211 tests, 4,440 rows in results.csv. Next: M9 is blocked (C-47); the owner must decide how to proceed (see report). |
