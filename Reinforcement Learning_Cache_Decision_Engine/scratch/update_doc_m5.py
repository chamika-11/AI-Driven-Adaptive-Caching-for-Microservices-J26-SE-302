import pathlib

p = pathlib.Path("IMPLEMENTATION_DECISIONS.md")
s = p.read_text(encoding="utf-8")


def rep(old, new):
    global s
    n = s.count(old)
    assert n == 1, (n, old[:100])
    s = s.replace(old, new)


# ---- banner ---------------------------------------------------------------------------------
a = s.index("> **Status 2026-10-15:")
b = s.index("\n", a)
s = s[:a] + ("> **Status 2026-10-15: M0–M5 implemented and gated; M6 (baselines + evaluation runner + results.csv) not "
             "started. No learned agent exists.** `pytest`: **161 passed** (`.venv`, Python 3.12.0, torch 2.14.1+cpu). "
             "Primary staleness regime is pre-registered (`docs/PREREGISTRATION.md`). No real-trace *experiment* has been "
             "run (§2b, `docs/DATA_ACCESS.md`); every number so far is synthetic. Evidence documents: "
             "`docs/M4_SIM_DIAGNOSTIC.md`, `docs/PLACEMENT_SIGNAL.md`, `docs/REWARD_SCALING.md`. A requirement is marked "
             "`DONE` only with the test that proves it named next to it.") + s[b:]

# ---- R-P7 / R-P8 / R-S ----------------------------------------------------------------------
rep("| R-P7 | Normaliser statistics from training portion only; frozen at evaluation; shipped inside the checkpoint. | MD Correction 6, Overhead | NOT STARTED |",
    "| R-P7 | Normaliser statistics from training portion only; frozen at evaluation; shipped inside the checkpoint. | MD Correction 6, Overhead | **DONE for the normaliser (tests: `test_frozen_normalizer_does_not_change_and_round_trips`, `test_normalizer_is_learned_only_from_the_training_pass`)** — `state_dict()` round-trips; the checkpoint file format is M9. |")
rep("| **PARTIAL** — predictor-table leakage tested (R-P3 tests); the 19-feature builder does not exist yet, so the feature-level leakage test is pending (M5). |",
    "| **DONE (tests: `test_no_feature_depends_on_future_requests`, `test_features_match_independent_brute_force_at_every_decision`, plus the R-P3 predictor tests)** — scrambling every request after a cut-off leaves all earlier observations bit-identical. |")
rep("| **PARTIAL** — the engine has no episodes and closes open insertions as `truncated` at run end (test `test_every_insertion_is_closed_exactly_once`); the `done`-flag handling is an M5/M9 concern. |",
    "| **DONE for assembly (tests: `test_no_transition_is_ever_terminal_and_window_ends_are_not_done`, `test_transition_assembly_invariants`)**: `done` is always False; end-of-run insertions are dropped and counted, never stored as terminal. The replay/target side (no bootstrap cut) is M9. |")
a = s.index("| R-S6 | Pending-transition mechanism:")
b = s.index("\n", a)
s = s[:a] + ("| R-S6 | Pending-transition mechanism: store (s, a, t_decision) + accumulators (hits, byte-seconds, backend fetches, stale reads); close at first of eviction / invalidation / expiry / hard cap 7200 s. | MD Credit assignment | "
             "**DONE (tests: `test_transition_assembly_invariants`, M4 lifecycle tests)** — `(s, a, r, s')` assembled at closure; closes when the LAST copy is gone (D-24). |") + s[b:]
rep("| R-S8 | Monitoring queue: when chosen TTL is shorter than true lifetime, observe what longer TTL would have earned. | MD Credit assignment (RLCache) | NOT STARTED |",
    "| R-S8 | Monitoring queue: when chosen TTL is shorter than true lifetime, observe what longer TTL would have earned. | MD Credit assignment (RLCache) | **NOT STARTED — deferred** (needs counterfactual replay; revisit only if the plain agent fails to learn TTL ordering). |")
rep("| R-S9 | `s'` = global state at resolution time; semi-MDP; optional time-based discount (see C-17). | MD Credit assignment | NOT STARTED |",
    "| R-S9 | `s'` = global state at resolution time; semi-MDP; optional time-based discount (see C-17). | MD Credit assignment | **DONE as D-9 (test: `test_transition_assembly_invariants`)**: `s'` = observation at the next decision after closure; `dt` stored per transition for the D-11 ablation. |")
rep("| R-S16 | Bounded per-key metadata (no unbounded `recency`/`freq` dicts). | MD Phase 5 diagnostics | NOT STARTED |",
    "| R-S16 | Bounded per-key metadata (no unbounded `recency`/`freq` dicts). | MD Phase 5 diagnostics | **DONE (by construction; tests: `test_long_window_slides`)** — per-key arrays are O(n_keys), windows are fixed rings. Metadata bytes are not yet charged against capacity (R-E8). |")
rep("| R-S17 | Gymnasium-compatible adapter passing `check_env` (for API hygiene and SB3 cross-checks). | MD Phase 2 | NOT STARTED |",
    "| R-S17 | Gymnasium-compatible adapter passing `check_env` (for API hygiene and SB3 cross-checks). | MD Phase 2 | **DONE (tests: `test_check_env_passes`, `test_env_reset_is_deterministic_and_obs_in_space`, `test_env_episode_semantics_and_reward_accounting`)**; reward semantics differ from textbook Gym on purpose (see `env.py` docstring, D-2). |")

# ---- R-F rows (each one) ---------------------------------------------------------------------
feat = {
    "R-F1": ("log recency gap 1, `log1p(Δt)/log1p(Δt_max)` clip [0,1]", "`test_recency_gaps_and_sentinels`"),
    "R-F2": ("log recency gap 2, sentinel 1.0 if never seen", "`test_recency_gaps_and_sentinels`"),
    "R-F3": ("count of this key in last 10 requests ÷ 10", "`test_window_counts_and_decision_request_excluded`"),
    "R-F4": ("count in last 100 ÷ 100", "`test_window_counts_and_decision_request_excluded`"),
    "R-F5": ("count in last 1000 ÷ 1000", "`test_window_counts_and_decision_request_excluded`, `test_long_window_slides`"),
    "R-F6": ("EDC, ~60 s half-life ÷ running max", "`test_edc_decays_with_half_life`"),
    "R-F7": ("object size `log1p(bytes)/log1p(max)`", "`test_sim_and_predictor_features_pass_through`"),
    "R-F8": ("backend fetch latency for this key (log-scaled) — see A-4", "`test_sim_and_predictor_features_pass_through`, `test_per_key_backend_latency_varies_and_is_seeded`"),
    "R-F9": ("predicted TTL `log1p/log1p(3600)`", "`test_sim_and_predictor_features_pass_through`"),
    "R-F10": ("per-key write rate (\"volatility\")", "`test_sim_and_predictor_features_pass_through`"),
    "R-F11": ("cache utilisation (bytes)", "`test_sim_and_predictor_features_pass_through`"),
    "R-F12": ("hit ratio over last 1000 requests (**hit ratio only**)", "`test_hit_ratio_counts_reads_only`"),
    "R-F13": ("request rate (log-scaled)", "`test_rate_cov_and_invalidation_rate`"),
    "R-F14": ("rate CoV over 10 s", "`test_rate_cov_and_invalidation_rate`"),
    "R-F15": ("rate CoV over 300 s", "`test_cov300_uses_ten_second_sums`"),
    "R-F16": ("top-10-key share of last 1000 requests", "`test_top10_share`"),
    "R-F17": ("global invalidation rate (log-scaled)", "`test_rate_cov_and_invalidation_rate`"),
    "R-F18": ("normalised backend load (in-flight / max concurrency) — see C-20", "`test_inflight_counts_open_fetch_windows`, `test_sim_and_predictor_features_pass_through`"),
    "R-F19": ("hot-key flag from predictor {0,1}", "`test_hot_flag_top_one_percent_and_tie_handling`"),
}
for rid, (txt, tests) in feat.items():
    rep(f"| {rid} | {txt} | NOT STARTED |",
        f"| {rid} | {txt} | **DONE** (hand-computed: {tests}; cross-checked against an independent brute force by `test_features_match_independent_brute_force_at_every_decision` where applicable) |")
rep("| R-F20 | Normalisation: running z-score clip [−5, 5] (Welford over EMA α≈1e-4) for unbounded features, fixed min-max for bounded; frozen at eval; declared own contribution. | NOT STARTED |",
    "| R-F20 | Normalisation: running z-score clip [−5, 5] (Welford over EMA α≈1e-4) for unbounded features, fixed min-max for bounded; frozen at eval; declared own contribution. | **DONE (tests: `test_zscore_features_are_centered_and_clipped`, `test_frozen_normalizer_does_not_change_and_round_trips`, `test_observation_shape_names_and_ranges`)** — z-score (÷5) on backend latency, request rate, invalidation rate; running max on EDC and size; the rest fixed. |")

# ---- R-R rows ---------------------------------------------------------------------------------
rep("| NOT STARTED |\n| R-R2 |", "| X |\n| R-R2 |") if False else None
r = {
    "R-R1": "**DONE (tests: `test_reward_hand_computed`, `test_creating_miss_is_charged_only_through_the_backend_term`, `test_more_hits_raise_reward_monotonically`)** with read-level terms summed per D-10 and the learner-facing scaling of D-32.",
    "R-R2": "**DONE (tests: `test_reward_weights_match_spec_and_enforce_ordering`)**; `w_stale > w_hit` enforced.",
    "R-R3": "**DONE (tests: `test_utilisation_gate_and_stampede_outside_gate`, `test_full_cache_lowers_reward_relative_to_empty_for_the_same_outcome`)**; gate evaluated at decision time; `gate_enabled=False` ablation. See C-40.",
    "R-R4": "**DONE (tests: `test_reward_hand_computed`, `test_utilisation_gate_and_stampede_outside_gate`)** — `F_ref = concurrent + hits` per insertion window.",
    "R-R5": "**DONE with a revision (D-32)**: learner reward = `clip(raw/100, ±10)`; pre-clip `raw` is stored on every transition (test `test_reward_summary_preclip_histogram_is_recorded`, `test_scaling_clipping_and_preclip_value_preserved`); clip-fraction study in `docs/REWARD_SCALING.md`.",
    "R-R7": "**Wording decision recorded in `reward.py` docstring**; thesis text pending.",
}
for rid, txt in r.items():
    a = s.index(f"| {rid} |")
    b = s.index("\n", a)
    line = s[a:b]
    assert line.endswith("| NOT STARTED |"), line[-60:]
    s = s[:a] + line[: -len("NOT STARTED |")] + txt + " |" + s[b:]

# ---- decisions -----------------------------------------------------------------------------------
rep("| D-18 | Proposed repository layout:",
    "| D-31 | **Primary staleness regime = `harsh`** (`lossy`, p_inv_l1 0.2, d_inv_l1 10 s, p_bypass 0.3); `lossy` default and `ttl_only` are declared sensitivity arms; it is the built-in `Config()` default. Chosen by the owner 2026-10-15 AFTER the fixed-rule signal scan (disclosed in `docs/PREREGISTRATION.md`) and before any learned-agent run. | C-38, Q-8 | ACTIVE |\n"
    "| D-32 | **Learner-facing reward = `clip(raw / 100, ±10)`** with D-10 summation, gate retained. Literal D-10 (`clip(raw, ±10)`) is REJECTED. | `docs/REWARD_SCALING.md`: D-10's >5% trigger fired (5.69% at 25% capacity, long TTL); literal clip was ~3 SE below the best fixed action out of sample; `div100_clip` was the best bounded candidate under the pre-declared rule. Criterion (a)'s wording admitted the unbounded `raw` vacuously; applied as intended (bounded), disclosed. | ACTIVE |\n"
    "| D-33 | Per-key backend latency is simulated: `backend_us × LogNormal(mean 1, sigma 0.5)`, fixed per key from `LatencyConfig.seed`, used for the fetch window, miss latency and feature #8. `backend_sigma = 0` is the constant ablation (A-4). | Otherwise feature #8 would be a constant (dead input). | ACTIVE |\n"
    "| D-34 | The simulator loop is resumable (`begin` / `next_decision` / `commit`) and `run()` is built on it; an `observer` receives every processed request. The feature tracker is fed by the observer AFTER a request and queried at the decision BEFORE the request is recorded (D-21). | Lets the trainer and the Gymnasium adapter own the control flow. | ACTIVE |\n"
    "| D-35 | Rate windows use a 301-slot ring (300 completed seconds + the in-progress second). | The first version used 300 slots, which aliased the oldest second onto the current partial second; found by the brute-force cross-check. | ACTIVE |\n"
    "| D-18 | Proposed repository layout:")

# ---- contradictions -------------------------------------------------------------------------------
rep("| C-32 | Responsibility table:",
    "| C-39 | — (MD reward table) | `w_mem · bytes_held·seconds_held / (capacity · T_window)` is presented as a term that charges memory use. | With `capacity` = total cache bytes and `T_window` = 3600 s, one decision's term is ~10⁻⁴ of its hit term: mean contribution < 0.0001 (`docs/REWARD_SCALING.md`). The memory objective is inert as specified; a `w_mem` sweep would be meaningless. A different normalisation (e.g. per-decision mean byte-seconds) is a design choice for the owner. | **OPEN** |\n"
    "| C-40 | — (R-R3, MD correction six) | A utilisation gate `u = 1 − (util − 0.9)/0.1` that \"collapses reward only as the cache approaches full\". | In a capacity-constrained cache with eviction the cache is full in steady state: 97.7% of decisions under a long-TTL policy were taken at utilisation > 0.9, and `u` reaches 0 at a full cache. Measured effect on action ranking is nil (removing it moved alignment by < 1 SE), so R-R3 is kept and `gate_enabled=False` is an ablation arm. | OPEN (conceptual); no action needed for correctness |\n"
    "| C-32 | Responsibility table:")

rep("| Q-8 | **Which staleness regime is primary?**",
    "| Q-8 | ~~**Which staleness regime is primary?**")
rep("| **Yes — before any learned-agent run** | Pre-register `harsh` as primary and report `lossy` and `ttl_only` as declared sensitivity arms; decide the sidecar question with the supervisor. |",
    "| **Yes — before any learned-agent run** | Pre-register `harsh` as primary and report `lossy` and `ttl_only` as declared sensitivity arms; decide the sidecar question with the supervisor. |~~ **RESOLVED 2026-10-15 by D-31** (regime). The per-service-sidecar modelling question (A-7) and the real LMS invalidation reliability remain open for the supervisor. |")

# ---- gate evidence in section 9 -----------------------------------------------------------------------
a = s.index("| M5 | Feature tracker (bounded)")
b = s.index("\n", a)
line = s[a:b]
assert line.endswith("| here |"), line[-40:]
s = s[:a] + line[:-len("| here |")] + ("| here — **GATE PASSED 2026-10-15** (`tests/test_features.py` 15, "
                                        "`tests/test_reward_transitions_env.py` 15; full suite 161 passed). Pre-clip histogram: "
                                        "`docs/REWARD_SCALING.md` |") + s[b:]

s = s.rstrip("\n") + "\n" + (
    "| 2026-10-15 | **M5 implemented and gated; primary staleness regime pre-registered (D-31).** New: "
    "`src/rlcache/{features,reward,transitions,runner,env}.py`; engine gained per-key backend latency, a resumable "
    "`begin/next_decision/commit` loop and an observer hook (`tests/test_simulator.py` +3 tests, 3 white-box tests "
    "rewritten); `tests/{test_features,test_reward_transitions_env}.py`; `scripts/reward_scaling.py`; "
    "`docs/{PREREGISTRATION,REWARD_SCALING}.md`. `pytest`: **161 passed**; mutation checks on window, gate and `s'` were "
    "all caught. Found: (i) rate-window aliasing bug (300-slot ring) caught only by the full-trace brute-force "
    "cross-check (D-35); (ii) D-10 literal clipping rejected (D-32); (iii) memory term inert (C-39); (iv) gate pinned "
    "near 0 in steady state but with no measurable ranking effect (C-40); (v) 1% of decisions carry 73–84% of total "
    "reward; (vi) class-level agents gain at most ~+0.006 U/read over the best fixed action, so expect small learned-agent "
    "margins. A post-hoc gate-off arm was added after seeing results and is labelled as such (Addendum A). Next: M6 "
    "(non-learned baselines, evaluation runner, results.csv writer, F2/T2 script). |\n")
p.write_text(s, encoding="utf-8")
print("ok", len(s))
