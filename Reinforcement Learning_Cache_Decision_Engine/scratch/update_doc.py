import pathlib

p = pathlib.Path("IMPLEMENTATION_DECISIONS.md")
s = p.read_text(encoding="utf-8")


def rep(old, new):
    global s
    n = s.count(old)
    assert n == 1, (n, old[:80])
    s = s.replace(old, new)


# ---- header banner ------------------------------------------------------------------------
rep("> **Status at creation: nothing is implemented and nothing has been tested.** Every requirement below is `NOT STARTED`. The only verified facts are the environment checks in §2, run on 2026-10-14. No statement in this file that something \"works\" is permitted until the test that proves it is named next to it.",
    "> **Status 2026-10-15: M0–M3 implemented and gated; M4 (simulator) not started.** `pytest`: **87 passed** (`.venv`, Python 3.12.0, torch 2.14.1+cpu). Nothing involving the simulator, features, reward, baselines, tabular Q or DQN exists yet. Real-trace *experiments* have NOT been run (see §2b and `docs/DATA_ACCESS.md`). A requirement is marked `DONE` only with the test that proves it named next to it.")

# ---- section 2b ---------------------------------------------------------------------------
rep("---\n\n## 3. Requirements register",
    """### 2b. Environment facts verified 2026-10-15 on the user's PC (supersede the cloud-workspace rows above)

| Check | Result | Consequence |
|---|---|---|
| Python | 3.12.0 (Windows, `.venv` in project root) | — |
| `pip install` torch 2.14.1 (CPU wheel), gymnasium 1.4.0, numpy 2.5.4, pandas 3.0.6, scipy, zstandard, tensorboard | **Succeeded** (first attempt failed on a transient DNS error for `files.pythonhosted.org`; retry succeeded) | **D-3 is SUPERSEDED**: DQN code can be executed and tested on this machine. |
| CMU PDL FTP | Reachable, but `twemcacheWorkload` is a **dangling symlink** (`550 No such file or directory`) | Full shards unobtainable via the documented path. |
| SNIA IOTTA | Anti-bot JS challenge + licence acceptance | Needs the owner in a browser. |
| `twitter/cache-trace` repo `samples/2020Mar/` | **Reachable**; cluster012 / cluster052 / cluster022 downloaded (66 / 44 / 74 MB, plain text) | Schema proven (R-D1). Samples are 1M rows spanning only 58–553 s (not usable for TTL-expiry or per-key volatility experiments). |
| libcachesim, rliable, d3rlpy | **Not installed** on this machine | Needed from M11 / M12 only. |

---

## 3. Requirements register""")

# ---- R-D rows -----------------------------------------------------------------------------
rep("| R-D1 | Obtain one plain-text Twitter Twemcache shard with `op` and `TTL` columns (CMU PDL FTP → SNIA IOTTA → repo `samples/`); prove with 5 printed rows, nonzero TTL on `set`. | MD Correction 1, Phase 0 | NOT STARTED |",
    "| R-D1 | Obtain one plain-text Twitter Twemcache shard with `op` and `TTL` columns (CMU PDL FTP → SNIA IOTTA → repo `samples/`); prove with 5 printed rows, nonzero TTL on `set`. | MD Correction 1, Phase 0 | **DONE for the schema, via repo `samples/` only** (test: `test_real_cluster012_prefix_schema`; 5 rows printed by `scripts/profile_trace.py`; evidence `docs/DATA_ACCESS.md`). Full shards: BLOCKED (FTP symlink dangling; SNIA needs browser + licence). |")
rep("| R-D2 | Never decompress a whole shard; stream in chunks; slice contiguous time windows. | MD Phase 0/1 | NOT STARTED |",
    "| R-D2 | Never decompress a whole shard; stream in chunks; slice contiguous time windows. | MD Phase 0/1 | **DONE (tests: `test_time_window_and_early_stop`, `test_zstd_stream_matches_plain`, `test_max_rows`)**. Early stop at `t_end` and `.zst` streaming verified on fixtures; never exercised on a real multi-GB `.zst` (none available). |")
rep("| R-D3 | Streaming parser for schema `ts,key,key_size,val_size,client_id,op,ttl`; 11-op vocabulary; write set = {set, add, replace, cas, append, prepend, incr, decr, delete}. | MD Phase 1 | NOT STARTED |",
    "| R-D3 | Streaming parser for schema `ts,key,key_size,val_size,client_id,op,ttl`; 11-op vocabulary; write set = {set, add, replace, cas, append, prepend, incr, decr, delete}. | MD Phase 1 | **DONE (tests: `test_all_eleven_operations_recognised`, `test_read_write_classification`, `test_namespace_delimiter_inference_not_always_colon`, `test_malformed_rows_counted_and_limit_enforced`)**. Delimiter inference also checked by hand on the real keys: cluster012 hashed → none, cluster052 `:`, cluster022 `|`. |")
rep("| R-D4 | Forward-fill last write's TTL onto later reads as `ttl_label`. | MD Phase 1 | NOT STARTED |",
    "| R-D4 | Forward-fill last write's TTL onto later reads as `ttl_label`. | MD Phase 1 | **DONE (test: `test_ttl_label_forward_fill_is_causal`)** — causal (uses only earlier writes). |")
rep("| R-D5 | Sampling only by contiguous time window or key-space hash sampling **with capacity scaled by the same fraction**; never uniform row sampling. | MD Phase 1 | NOT STARTED |",
    "| R-D5 | Sampling only by contiguous time window or key-space hash sampling **with capacity scaled by the same fraction**; never uniform row sampling. | MD Phase 1 | **DONE (test: `test_key_hash_sampling_keeps_whole_keys_and_records_fraction`)**. `scaled_capacity()` exists; the simulator must call it (M4). |")
rep("| R-D6 | Primary training trace cluster12 (write-heavy); evaluation cluster52 (fallback cluster22); one daytime-peak and one overnight window. | MD \"Data\" | NOT STARTED |",
    "| R-D6 | Primary training trace cluster12 (write-heavy); evaluation cluster52 (fallback cluster22); one daytime-peak and one overnight window. | MD \"Data\" | **BLOCKED** — only 1–9 minute samples obtained; daytime/overnight windows need the full shards (Q-2). Parser ready. |")
rep("| R-D7 | Synthetic generator: truncated Zipf α ∈ {0.6, 0.8, 0.99, 1.2}; ~0.3 probability temporal-locality redraw from last ~1000 keys; **per-key lognormal write rate**; diurnal, flash-crowd, popularity-shift, write-rate-shift injectors. | MD \"Data\", Adaptation | NOT STARTED |",
    "| R-D7 | Synthetic generator: truncated Zipf α ∈ {0.6, 0.8, 0.99, 1.2}; ~0.3 probability temporal-locality redraw from last ~1000 keys; **per-key lognormal write rate**; diurnal, flash-crowd, popularity-shift, write-rate-shift injectors. | MD \"Data\", Adaptation | **DONE (tests: `test_per_key_write_rate_spread`, `test_zipf_alpha_controls_skew`, `test_temporal_locality_increases_window_reuse`, `test_popularity_shift_changes_hot_set`, `test_flash_crowd_concentrates_traffic`, `test_write_rate_shift_multiplies_writes`, `test_time_to_next_write_spans_ttl_decades`)**. Diurnal is a sinusoidal arrival intensity; its effect has no dedicated test yet. |")
rep("| R-D9 | Oracle annotations: `next_access_vtime` and `next_write_vtime` per request (two-pass), for Belady, TTL oracle, TTL-constrained Belady. | MD Phase 3 | NOT STARTED |",
    "| R-D9 | Oracle annotations: `next_access_vtime` and `next_write_vtime` per request (two-pass), for Belady, TTL oracle, TTL-constrained Belady. | MD Phase 3 | **DONE (test: `test_oracle_matches_brute_force_on_small_trace`)**; Belady/TTL-Belady consumers not yet built. |")
rep("| R-D10 | Verify volatility varies across keys (distribution plot); if near-constant, switch to a write-heavier cluster. | MD Phase 1 | NOT STARTED |",
    "| R-D10 | Verify volatility varies across keys (distribution plot); if near-constant, switch to a write-heavier cluster. | MD Phase 1 | **Synthetic: DONE (test: `test_fitted_volatility_varies_across_keys`). Real: FAILS on the samples** — median 1 write per key in cluster012/052 (`docs/DATA_ACCESS.md`); needs the full shards. No plot produced yet. |")

# ---- R-P rows -----------------------------------------------------------------------------
rep("| R-P1 | `compute_volatility` (0.5·squashed write rate + 0.3·write ratio + 0.2·CV of inter-write gaps), declared as **this project's own** definition. | MD Phase 1 | NOT STARTED |",
    "| R-P1 | `compute_volatility` (0.5·squashed write rate + 0.3·write ratio + 0.2·CV of inter-write gaps), declared as **this project's own** definition. | MD Phase 1 | **DONE (tests: `test_volatility_hand_computed_and_bounded`, `test_volatility_orders_keys_by_write_rate`)** |")
rep("| R-P2 | `compute_predicted_ttl` = 20th percentile of inter-write gaps, clipped [1, 3600]; never-written keys → 3600. | MD Phase 1 | NOT STARTED |",
    "| R-P2 | `compute_predicted_ttl` = 20th percentile of inter-write gaps, clipped [1, 3600]; never-written keys → 3600. | MD Phase 1 | **DONE (tests: `test_predicted_ttl_hand_computed`, `test_group_quantile_matches_numpy`)** |")
rep("| R-P3 | Frozen split: predictor statistics fitted on trace[0:30%], frozen; agent trained on later data; test touched once. | MD Correction 6, Evaluation | NOT STARTED |",
    "| R-P3 | Frozen split: predictor statistics fitted on trace[0:30%], frozen; agent trained on later data; test touched once. | MD Correction 6, Evaluation | **Predictor part DONE (tests: `test_fit_ignores_everything_after_fit_end`, `test_fit_on_prefix_equals_fit_on_longer_trace`, `test_tables_are_frozen`)**; \"test touched once\" is a protocol enforced at M6/M10, not yet implemented. |")
rep("| R-P4 | `synthetic_predictor(accuracy)` interpolating truth with a **shuffled** copy (preserves marginal). | MD Phase 1 | NOT STARTED |",
    "| R-P4 | `synthetic_predictor(accuracy)` interpolating truth with a **shuffled** copy (preserves marginal). | MD Phase 1 | **DONE with a deviation (C-33)** (tests: `test_accuracy_one_equals_truth`, `test_accuracy_zero_is_permutation_same_marginal`, `test_mixture_preserves_marginal_at_intermediate_accuracy`, `test_interpolate_mode_shrinks_variance_contradicting_md_claim`). Default is `mixture`, not the MD's literal interpolation. |")
rep("| R-P6 | Agent fully functional with predictor absent (defaults). | MD contracts; Proposal NFR5 | NOT STARTED |",
    "| R-P6 | Agent fully functional with predictor absent (defaults). | MD contracts; Proposal NFR5 | **Tables DONE (test: `test_absent_predictor_is_constant_and_documented`)**; agent-level behaviour untested (no agent yet). |")
rep("| R-P8 | Leakage test: no feature at decision time may depend on any request with index > current. | MD Correction 6; Proposal NFR9, Validation 7 | NOT STARTED |",
    "| R-P8 | Leakage test: no feature at decision time may depend on any request with index > current. | MD Correction 6; Proposal NFR9, Validation 7 | **PARTIAL** — predictor-table leakage tested (R-P3 tests); the 19-feature builder does not exist yet, so the feature-level leakage test is pending (M5). |")

# ---- R-A rows -----------------------------------------------------------------------------
rep("| R-A1 | `encode_action(p,t,e) = p*15 + t*3 + e`; `decode_action` inverse; round-trip test over all 45. | NOT STARTED |",
    "| R-A1 | `encode_action(p,t,e) = p*15 + t*3 + e`; `decode_action` inverse; round-trip test over all 45. | **DONE (tests: `test_round_trip_all_digit_triples`, `test_round_trip_all_action_ids`, `test_stride_order_matches_spec`, range/type rejection tests)** |")
rep("| R-A2 | TTL buckets {5, 30, 120, 600, 3600} s (live demo variant: see C-23). | NOT STARTED |",
    "| R-A2 | TTL buckets {5, 30, 120, 600, 3600} s (live demo variant: see C-23). | **DONE (test: `test_space_is_exactly_45`)** |")
rep("| R-A3 | Priority levels {low, normal, high} → eviction-score multipliers (values: A-6). | NOT STARTED |",
    "| R-A3 | Priority levels {low, normal, high} → eviction-score multipliers (values: A-6). | **Constants DONE (test: `test_cache_capacity_ratio`)**; multiplier effect on eviction needs M4. |")
rep("| R-A4 | Placement {local, redis, both}. | NOT STARTED |",
    "| R-A4 | Placement {local, redis, both}. | **Codec DONE (test: `test_decode_semantics` — local writes only L1, redis only L2)**; semantics inside the simulator pending (M4). |")
rep("| R-A5 | No admission (\"do not cache\") action; stated as scoped limitation. | NOT STARTED |",
    "| R-A5 | No admission (\"do not cache\") action; stated as scoped limitation. | **DONE (by construction: 45 actions, test `test_space_is_exactly_45`)** |")

# ---- R-F ----------------------------------------------------------------------------------
rep("### 3.4 State (R-F) — the 19 features\n",
    "### 3.4 State (R-F) — the 19 features\n\n**Names, order, blocks and the single as-of-timestamp convention are DONE** in `src/rlcache/features_spec.py` (tests: `test_exactly_19_features_in_three_blocks`, `test_no_miss_ratio_and_no_key_identity_features`, `test_tabular_feature_indices_fix_prototype_bug`, `test_state_ladder_is_strictly_nested`). **No feature VALUE is computed yet** — every row below stays `NOT STARTED` until the M5 tracker exists with hand-computed unit tests.\n")

# ---- R-E12 --------------------------------------------------------------------------------
rep("| R-E12 | Artefacts T1–T9 and F1–F11 regenerated from one `results.csv` by one command. | NOT STARTED |",
    "| R-E12 | Artefacts T1–T9 and F1–F11 regenerated from one `results.csv` by one command. | **Schema DONE (tests: `test_results_round_trip`, `test_results_rejects_bad_rows`, `test_results_has_no_comparable_reward_column`)**; no generator script yet. |")

# ---- decisions ----------------------------------------------------------------------------
rep("Torch cannot be installed in this workspace (§2). | ACTIVE |",
    "Torch cannot be installed in this workspace (§2). | **SUPERSEDED by D-19** |")
rep("| D-18 | Proposed repository layout:",
    "| D-19 | Torch 2.14.1+cpu is installed in the project `.venv` on the user's PC (§2b); DQN code is executed and tested there. WSL2 is not required (libcachesim, if wanted, is the only thing that would need it). | Verified by import + forward pass 2026-10-15. | ACTIVE |\n"
    "| D-20 | **Staleness model (Q-3 resolved by the user's instruction \"configurable staleness model\")**: `StalenessConfig(mode, p_inv_l1, d_inv_l1_s, p_bypass)` with modes `lossy` (primary, option (c)), `ttl_only`, `perfect`. Default values p_inv_l1 = 0.5, d_inv_l1 = 2 s, p_bypass = 0.05 are **placeholders** and must be swept; they are not calibrated to any system. | C-6 | ACTIVE (config DONE, mechanism pending M4) |\n"
    "| D-21 | A feature's as-of time is the decision request's index `i`; every window is over requests with index `< i` (request `i` itself excluded). | Gives all 19 features one interpretation; makes the leakage property checkable (`features_spec.py` docstring). | ACTIVE |\n"
    "| D-22 | Default synthetic workload: 4,000 keys, 600,000 requests, 8 h, α = 0.99, write-interval median 2 h with lognormal σ = 2.0 (~19% writes). Chosen so that read-weighted time-to-next-write covers all five TTL decades (0.5% / 2% / 5% / 16% / 31% / 45% for <5 s / 5–30 / 30–120 / 120–600 / 600–3600 / >3600 s). | Prevents a single TTL bucket being trivially optimal (D-15). Values are tuning choices, not sourced. | ACTIVE |\n"
    "| D-23 | Hot-key flag excludes ties at the cut-off (strictly greater than the (k+1)-th largest count). | An earlier `>=` version flagged 298/300 keys when counts tied (found by `test_hot_flag_top_one_percent_and_tie_handling`). | ACTIVE |\n"
    "| D-18 | Proposed repository layout:")

# ---- contradictions / questions -----------------------------------------------------------
rep("| C-32 | Responsibility table:",
    "| C-33 | — (MD Phase 1 `synthetic_predictor` docstring) | Claims interpolating truth with a shuffled copy keeps \"the marginal distribution identical at every accuracy level\". | **False** for `a*true + (1-a)*shuffled`: variance shrinks by `a² + (1-a)²` (test `test_interpolate_mode_shrinks_variance_contradicting_md_claim`). Default replaced by element-wise `mixture`, which preserves the marginal. The MD's literal version is kept as `mode=\"interpolate\"`. | RESOLVED |\n"
    "| C-34 | — | MD Phase 0 expects `ftp://…/twemcacheWorkload/open_source/` to list shards. | Directory is a dangling symlink on CMU's side (`docs/DATA_ACCESS.md`). Not a local problem. | OPEN (Q-2) |\n"
    "| C-35 | — | MD \"Data\" recommends cluster12/52 as multi-hour training/eval traces; the repo `samples/` fallback it lists in the risk register provides only 1M-row, 1–9 minute slices. | Samples validate the parser only; they cannot support TTL-expiry or volatility experiments. | OPEN (Q-2) |\n"
    "| C-32 | Responsibility table:")
rep("| (c), with (b) and \"perfect invalidation\" as sensitivity endpoints. |\n| Q-4",
    "| (c), with (b) and \"perfect invalidation\" as sensitivity endpoints. **RESOLVED 2026-10-15 by D-20** (user asked for a configurable model; all three modes are config options; values are placeholders). |\n| Q-4")
rep("| Try today; fall back to synthetic (MD Phase 0). |",
    "| **Answered partly 2026-10-15**: CMU FTP path is dangling; SNIA needs a browser (JS challenge + licence); repo samples obtained but too short. **Still needed:** fetch cluster12 / cluster52 `.zst` parts from SNIA IOTTA type 17 yourself, place under `data/raw/twitter_full/` (`docs/DATA_ACCESS.md`). |")

# ---- change log ---------------------------------------------------------------------------
s = s.rstrip("\n") + "\n" + (
    "| 2026-10-15 | **M0, M1, M2, M3 implemented and gated.** Files: `pyproject.toml`, `requirements.txt`, "
    "`requirements-offline.txt`, `configs/default.yaml`, `src/rlcache/{config,actions,features_spec,results_schema}.py`, "
    "`src/rlcache/trace/{record,parser,synthetic,splits,oracle}.py`, `src/rlcache/predictor/standin.py`, "
    "`scripts/profile_trace.py`, `tests/{test_actions,test_config_and_schema,test_trace_parser,"
    "test_synthetic_split_oracle,test_predictor}.py`, `tests/fixtures/twitter_mini.csv`, `docs/DATA_ACCESS.md`. "
    "`pytest`: **87 passed**. Failures found and fixed along the way: (i) hot-key flag flagged tied keys (code bug, D-23); "
    "(ii) six test-expectation errors of mine (fixture key/row counts, a too-small bad-row limit, a locality metric "
    "insensitive under Zipf, a flash-crowd baseline bound, an over-write-heavy oracle fixture). Real Twitter samples "
    "obtained (R-D1 schema proven) but unusable for TTL/volatility experiments (C-35). Torch installed (D-19). "
    "Next: M4 simulator. |\n")
p.write_text(s, encoding="utf-8")
print("ok", len(s))
