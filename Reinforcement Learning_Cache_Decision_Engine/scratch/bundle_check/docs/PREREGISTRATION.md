# Pre-registration (made 2026-10-15, before any learned-agent run)

Status: **no DQN, tabular-Q or bandit agent has been trained or evaluated at the time of
writing.** The only measurements that exist are fixed-rule simulator diagnostics on synthetic
data (`docs/M4_SIM_DIAGNOSTIC.md`, `docs/PLACEMENT_SIGNAL.md`).

## 1. Primary staleness regime (decided by the owner, 2026-10-15)

| arm | role | mode | `p_inv_l1` | `d_inv_l1` (s) | `p_bypass` |
|---|---|---|---:|---:|---:|
| **harsh** | **PRIMARY** | `lossy` | 0.2 | 10 | 0.3 |
| lossy | declared sensitivity arm | `lossy` | 0.5 | 2 | 0.05 |
| ttl_only | declared sensitivity arm | `ttl_only` | — | — | — |

* `harsh` is the built-in default of `Config()` (`config.STALENESS_PRESETS["harsh"]`).
* All three arms are reported for every headline comparison, whichever way they come out.
* The parameter values are placeholders chosen to represent "invalidation often fails or is
  late"; they are **not calibrated to any real system**. The real LMS/Redis invalidation
  reliability is an open question for the supervisor (Q-8).
* A `perfect`-invalidation arm exists as a unit-test endpoint (stale ≡ 0), not as a result arm.

## 2. Disclosure about how this regime was chosen

The choice was made *after* the fixed-rule signal scan in `docs/PLACEMENT_SIGNAL.md`, which
showed the TTL dimension carries far more usable signal when invalidation is unreliable
(`harsh`: +0.027 utility/read per-class; `lossy` default: +0.001…+0.004). It is therefore
pre-registered with respect to **learned-agent results**, not blind to the simulator's
behaviour. The reason for preferring it is that the research question (INV-8: Pareto
dominance in the (hit ratio, stale-read rate) plane from TTL + placement) is only non-trivial
when staleness has teeth; the `lossy` default and `ttl_only` arms bound the conclusion from
both sides.

## 3. What is committed to be reported regardless of outcome

* Results in all three arms, with `data_source` (synthetic / twitter_real) on every row.
* Placement-dimension findings including the expected "small / dominated" result (C-37).
* Any arm in which the learned agent fails to beat the best fixed TTL ladder point.
* Real-trace results only when full multi-hour shards exist (`docs/DATA_ACCESS.md`).

## 4. Still open (must be fixed before the first learned-agent run)

* **Q-7**: the "realistic" capacity that is the primary endpoint (proposal: L2 = 1% of unique
  footprint, L1 = 10% of L2). The signal studies show TTL has little room at ≤5% capacity, so
  this choice matters and is the owner's to make.
* **Reward scaling** (D-10 clip check) — decided by the pre-declared alignment criterion in
  `docs/REWARD_SCALING.md`, using development seeds 100–102 only.
* Evaluation seeds are 0–9; development seeds are 100+ and are never reported as results.

---

# Addendum M6 — primary capacity, evaluation protocol, baseline set (written 2026-10-15,
# BEFORE `scripts/run_baselines.py` exists or has been run)

Status at writing: no baseline has been evaluated on any evaluation seed or on any split.
Development scans (`docs/M4_SIM_DIAGNOSTIC.md`, `docs/PLACEMENT_SIGNAL.md`,
`docs/REWARD_SCALING.md`) used capacities 5% and 25% on seeds 0–2 or 100–102; the 1% capacity
named below has NEVER been simulated.

## M6-1. Primary capacity (closes Q-7)

**L2 = 1% of the trace's unique-object footprint (bytes); L1 = 10% of L2; staleness `harsh`.**

* Why this value: it is the value proposed in `IMPLEMENTATION_DECISIONS.md` Q-7 on 2026-10-14,
  before any simulator or experiment existed. (The MD only requires that one capacity be
  nominated in advance and lists 1% as one of six sweep points; it does not single out a
  value. "Realistic for a sidecar + shared cache" is the author's judgement, not a sourced
  figure.) It was **not** chosen from results, and it is the only candidate among {1, 5, 25}%
  for which I have seen no results.
* Honest cost, stated now: my own earlier scans found that at small capacities capacity evictions
  dominate TTL for the hit ratio (5%: every TTL ≥ 120 s gives the same OHR), so the primary
  endpoint is where a TTL-conditioned policy has the *least* room to raise hit ratio. Shorter
  TTLs may still lower staleness almost for free there, which is exactly the (hit ratio,
  stale-read) trade-off INV-8 is about, but a null result at the primary capacity is a real
  possibility and will be reported as such.
* **Secondary capacities, always reported alongside:** L2 = 5% and L2 = 25% (L1 = 10% of L2).
  The six-capacity sweep {0.1, 0.5, 1, 5, 10, 25}% is M11.
* Nothing about the primary capacity may be changed after baseline or agent results exist.
  If the 1% results are degenerate (e.g. L1 holds ≈ 4 objects), that is documented, not fixed
  by re-nominating a capacity.

## M6-2. Evaluation protocol

* Workload: `WorkloadConfig()` defaults (D-22), **evaluation seeds 0–9** (each seed is a distinct
  trace; the simulator seed equals the workload seed). Development seeds ≥ 100 stay off the
  results table.
* Split (D-8): predictor/statistics fit on request indices [0, 30%); validation [70%, 80%);
  **test [80%, 100%]**. Each evaluation run starts with a cold cache at the slice start, and the
  first 10% of the slice is excluded from the metrics (R-E2, fixed-fraction variant). The
  "filled k times" warm-up variant is a sensitivity check, not part of the primary table.
* Capacity is computed from the footprint of the WHOLE trace (a design parameter, not a learned
  quantity); it is the same for every policy (equal total capacity: L1 + L2).
* Cumulative reward is never reported next to heuristics. The scalar `U` (hit + latency −
  staleness, weights 1.0 / 0.5 / 3.0) is used only to select within a baseline family on the
  validation slice.

## M6-3. Baseline set (frozen list; every point is evaluated, none is dropped)

| family | points | notes |
|---|---:|---|
| `fixed` | 45 | every (placement, TTL bucket, priority) flat action; covers the "fixed-TTL ladder × placements" and the priority arms |
| `random` | 1 | uniform over the 45 actions (R-B1) |
| `stat_ttl` | 6 | per-key inter-write gap {mean, median, p10} from the fit slice, snapped to the nearest bucket in log space; placement {redis, both}; keys with no gap history get 3600 s |
| `pred_ttl` | 2 | the predictor's `predicted_ttl` snapped to a bucket (R-B6); placement {redis, both} |
| `aimd` | 4 | per-key TTL: +α s on a fresh-served insertion, ×β on any stale read; (α, β) ∈ {60, 300} × {0.5, 0.25}, start 120 s, placement redis |
| bounds (`policy_class = "bound"`) | 4 | zero-stale oracle TTL (placement redis, both: largest bucket ≤ time to next write); TTL-constrained Belady and plain Belady (unit-size object bound at equal capacity in objects) |

Total 58 learnable-free points + bounds. The tuning budget is therefore equal and explicit:
every family's whole grid is evaluated on test and enters the frontier; per-family scalar
comparisons use the grid point with the highest validation `U` (`best_by_val`).

## M6-4. Frontier and the primary statistic for any later learned agent

* Plane: x = stale-read rate (stale / reads), y = object hit ratio (hits / reads), per seed.
* **Baseline frontier** = the upper-left Pareto set of all non-bound baseline points, and its
  **upper concave envelope** ("randomised fixed policies": mixing two fixed policies per decision
  attains the segment between them, so a learned policy has to beat this, not just the
  staircase). Bounds are plotted but never enter the frontier.
* **Primary statistic**: `ΔOHR(s) = OHR_agent − OHR_frontier(stale_agent)` on the concave
  envelope (envelope extended horizontally to the right of its last vertex). For an agent whose
  stale rate is below every baseline's, the comparison is against the lowest-stale vertex and is
  reported as "beyond frontier" with its own flag. Paired by seed; summarised by the mean over
  the 10 seeds with a bootstrap 95% CI of the paired difference (rliable IQM etc. arrive in M11).
* "Pareto-dominates" is reported with both definitions (step set and envelope) and never
  collapsed into one number.

## M6-5. Not allowed after results exist

Editing the grids, dropping a point, changing the capacity, the staleness regime, the warm-up
fraction, the seeds, or the definition of the primary statistic. A baseline added later is
labelled `post-hoc` in `results.csv` (`notes`) and in every table that includes it.

---

# Addendum M6-B — nine post-hoc placement baselines (written 2026-10-15, BEFORE any
# evaluation seed 0–9 has been run; results.csv does not exist yet)

**Why this addendum exists.** After the first development run (seed 100 only, L2 = 1%) I found
that `random:45` beat every one of the 45 fixed actions (OHR 0.344 vs ≤ 0.331 on the test
slice). A diagnostic (`scratch/random_diag.py`, dev seed 100) attributed the gain to
**placement mixing**: random over placements alone gives 0.344, random over TTL alone 0.325,
random over priority alone 0.335, fixed `redis` 0.3285. Mixing `local` and `redis` entries uses
L1 and L2 as disjoint capacity, which no fixed action can (`redis` strands L1; `both`
duplicates). At 1% capacity the hit ratio is steep in capacity, so +10% effective capacity is
worth ≈ +1.6 pp OHR.

A baseline set without deliberate capacity-partitioning rules would therefore make a learned
policy look better than it is. The MD's placement lattice (R-B4: size threshold, frequency
threshold, hash-style partition) is the standard answer. Adding them makes the frontier
**harder** to beat, so this is the conservative direction; it is still a change made after
seeing a development result, so it is disclosed here and labelled.

| family | points | rule (TTL 600 s, normal priority) |
|---|---:|---|
| `place_hash` | 3 | a fixed fraction f ∈ {0.10, 0.25, 0.50} of keys (by a stable hash of the key id) go to `local`, the rest to `redis` |
| `place_size` | 3 | objects no larger than the {25th, 50th, 75th} percentile object size of the fit slice go to `local`, larger to `redis` |
| `place_freq` | 3 | `local` if the key was requested ≥ k ∈ {2, 3, 5} times in the last 1000 requests, else `redis` |

* All nine are flagged `post-hoc` in the `notes` column of `results.csv` and in every table.
* They join the baseline frontier like any other heuristic point (M6-4); `best_by_val` still
  picks one point per family on the validation slice.
* Frozen list size becomes 67 heuristic points + 4 bounds. No other point may be added.
* The dev-seed diagnostic itself is not a result and is not in `results.csv`.

**Consequence for the primary endpoint, stated now.** At L2 = 1% the TTL dimension is nearly
inert for both axes (every TTL ≥ 30 s gives the same OHR to three decimals; stale-read rate is
~0.04–0.06% for all of them), so the primary endpoint is mostly a test of *placement* and of
capacity use, not of TTL. The 5% and 25% arms (always reported) are where TTL has room. The
headline INV-8 claim may therefore be answered differently at different capacities, and the
write-up will say so.

---

# Addendum M7 — the no-DQN signal test (written 2026-10-15, BEFORE any M7 code exists or runs)

## Purpose

The MD's "cheat-agent test": if a policy that is handed an accurate predictor does not do
visibly better than the same policy handed an uninformative one, the features carry no signal
and no RL algorithm will help — so DQN work must stop and the features be fixed first. This test
is deliberately agent-free so a negative result cannot be blamed on a learner.

## Test policy and manipulation

* Policy: `pred_ttl:redis` (TTL = the bucket nearest the key's `predicted_ttl`, placement redis,
  normal priority). It is the simplest statistic-driven TTL rule and the one whose input is
  exactly the predictor feature (#9) the agent will see.
* Manipulation: `PredictorTables.fit(trace, fit_end)` (causal, fit slice only) degraded with
  `with_accuracy(a, rng, mode="mixture")`, a ∈ {0, 0.25, 0.5, 0.75, 1.0}. `mixture` preserves the
  marginal distribution exactly (C-33), so a change in outcome cannot be a change of input scale.
  The literal `interpolate` mode is reported as a secondary column only.
* a = 1.0 is the *fitted* (causal) predictor, not an oracle; a = 0 is a random permutation of its
  values across keys.

## Data and seeds

* **Development seeds 100–109** (ten distinct traces, `WorkloadConfig()` defaults). The
  evaluation seeds 0–9 are NOT touched by M7.
* Arm `harsh`; test slice [80%, 100%], cold start, first 10% excluded; simulator seed = trace seed
  (common random numbers across accuracies, so differences are paired).
* Capacities: **1% (primary, gating)**, 5% and 25% (reported; used only by the decision rule below).

## Gating criteria (all four must hold at the primary capacity)

Per seed `s`: `d_s = stale_rate(a=0) − stale_rate(a=1)`, `r_s = d_s / stale_rate(a=0)`.

| id | criterion |
|---|---|
| G1 | mean(d) > 0 and the 95% paired-bootstrap percentile CI (10,000 resamples, fixed RNG seed 0) has a lower bound > 0 |
| G2 | d_s > 0 in at least 8 of the 10 seeds |
| G3 | mean relative reduction mean(r_s) ≥ 0.20 (seeds with stale_rate(a=0) = 0 are excluded from this mean and counted) |
| G4 | mean[OHR(a=1) − OHR(a=0)] ≥ −0.01 (the accurate predictor must not buy lower staleness by giving up hit ratio) |

Non-gating, always reported: Spearman correlation between accuracy and seed-mean stale rate over
the 5 levels (dose response); the same four statistics at 5% and 25%; the `interpolate` column.

## Decision rule (fixed now)

* **PASS** — G1–G4 hold at 1%: proceed to M8 with the feature set as is.
* **PARTIAL** — G1–G4 fail at 1% but hold at BOTH 5% and 25%: proceed, but the write-up must say
  the primary endpoint carries no usable TTL-prediction signal (consistent with C-41: TTL is
  nearly inert at 1% capacity) and the 5%/25% arms become the evidence for the TTL claim.
* **FAIL** — G1–G4 fail at 1% and at least one of 5%/25% also fails: **stop agent work**;
  investigate predictor, generator and features before M8. No agent result may be produced.

## Secondary diagnostic (non-gating): do the 19 observation features predict the ideal TTL?

On dev seeds 100–102: collect `(obs, y)` at every decision of a `random:45` run on the training
slice [30%, 70%) and on the test slice, with `y = log1p(min(time to the key's next write, 3600 s))`
(the zero-stale TTL target; uses the future, for LABELS only). Fit a 2-hidden-layer MLP (64, 64)
on the training slice and report held-out R² on the test slice for: full observation with
a = 1.0; the same with a = 0.0; and with the three predictor features (#9, #10, #19) zeroed.
"Supportive" if R²(a = 1) − R²(a = 0) ≥ 0.05. This tests the *observations*, which the heuristic
above does not.

## Not allowed after results exist

Changing the policy, the accuracy grid, the seeds, the thresholds or the decision rule; adding
seeds to rescue a failing criterion. A repaired feature/predictor requires a NEW addendum and a
fresh set of development seeds (110–119), with the failed run kept in the record.

---

# Addendum M8 — tabular Q-learning (written 2026-10-15, BEFORE any agent code exists)

Context: M7 outcome was PARTIAL (`docs/M7_SIGNAL_TEST.md`); PyTorch is blocked on this machine
(C-47), so M9 cannot run, but tabular Q needs only numpy.

## Agent (R-L12, frozen)

* State: the five features `utilisation, hit_ratio, count_1000, volatility, predicted_ttl` (indices
  from `TABULAR_FEATURE_IDX`) of the normalised 19-vector, each into 4 bins → 4⁵ = 1024 states; 45 actions.
* Update: `Q[s,a] += α (r + γ max_a' Q[s',a'] − Q[s,a])`, α = 0.1, γ = 0.95 per decision (D-11),
  `r` = learner-facing reward `clip(raw/100, ±10)` (D-32); transitions assembled by D-9 (s' = next
  decision's observation); no `done`.
* Exploration: ε-greedy, ε 1.0 → 0.1 linearly over the first 30% of training decisions, then held at 0.1.
* Training budget: 300,000 decisions per (seed, capacity) by replaying the training slice
  [30%, 70%) from a cold cache as many times as needed (each replay restarts the simulator; the
  Q-table, normaliser and ε schedule persist; no terminal flag).
* **Calibration pass (before learning, training slice only):** a `random:45` run over the first
  40,000 requests of the training slice fits the normaliser (then FROZEN) and the bin edges.
* **Discretisations (both pre-registered):**
  * `qbin` — PRIMARY: equal-frequency bins; edges are the 25/50/75th percentiles of each feature
    over the calibration pass. This is this project's own construction: the MD's literal
    equal-width bins on [0, 1] are expected to degenerate (count_1000 = count/1000 and volatility
    are almost always in the lowest bin).
  * `ewidth` — the MD-literal equal-width bins; reported as the ablation that shows the
    degeneration (state-coverage figure).
* **Greedy evaluation:** ε = 0, Q frozen, cold start, 10% warm-up excluded, predictor = the fitted
  causal tables. A state never visited in training (all-zero visit count) falls back to the
  visit-weighted global-best action — stated so an untrained row cannot silently choose action 0.
* **Contextual-bandit arm (R-L13):** `qbin` with γ = 0, otherwise identical (`tabq:bandit`).

## Gate (dev seeds 100–109, validation slice, paired by seed)

`ΔU = U(tabq:qbin, greedy) − U(random:45)` with the same simulator seed.
Pass at a capacity iff mean ΔU > 0 AND the 95% paired-bootstrap CI (10,000 resamples, RNG seed 0)
has lower bound > 0 AND ΔU > 0 in ≥ 8 of 10 seeds.

* **PASS**: holds at the primary 1%. **PARTIAL**: fails at 1% but holds at 5% AND 25%.
* **FAIL**: otherwise → no evaluation-seed run; investigate on development seeds first.
* This is the §9 "beats random" bar, a LOW bar by design. Comparison against the best fixed
  action and against the baseline frontier is reported but is not part of the gate; the MD
  expects tabular Q to lose to the function-approximation agent and to be roughly a fixed-TTL
  heuristic.

## Evaluation-seed run (only if PASS or PARTIAL; once)

Seeds 0–9 × capacities {1%, 5%, 25%} × variants {`tabq:qbin`, `tabq:ewidth`, `tabq:bandit`} ×
splits {val, test}, arm `harsh`; per-(seed, capacity) training on that seed's training slice;
rows appended to `results/results.csv` with `policy_class = learned`, `family = tabular_q`.
Reported with the pre-registered per-seed paired ΔOHR statistic against the envelope of the
non-bound heuristics (M6-4) and with the placement-rule baselines of Addendum M6-B alongside.
No hyper-parameter (α, γ, ε, bins, budget) may be changed after the development gate is read.

## Amendment M8-a (written before any M8 run; no agent result existed)

* **Greedy eligibility.** At greedy-evaluation time only actions that received at least one
  Q-update in that state are eligible; if no action in the state has been tried, the fallback is
  the visit-weighted global-best action (as already stated for unvisited states). Reason: the
  scaled per-decision rewards are mostly slightly negative (a miss with no later hits gives
  ≈ −0.01), so the initial Q = 0 of an untried action would otherwise beat every tried action and
  the "greedy" policy would be an arbitrary untried action. During TRAINING the argmax runs over
  all 45 actions (the optimism then encourages trying them).
* Everything else in Addendum M8 is unchanged. The criterion, seeds, capacities and decision rule
  are as written above.


---

# Addendum M9 — Double Dueling DQN, run on Google Colab (written 2026-10-15, BEFORE any DQN
# code exists and before anything has been run)

## Where things run

* PyTorch cannot be imported on the development machine (C-47). The PyTorch code is therefore
  WRITTEN locally and EXECUTED on Colab (free CPU runtime). Nothing the PyTorch code produces
  counts as evidence until it has run there.
* To limit what can be wrong only on Colab, a pure-numpy reference learner with the same
  network, loss and optimiser formulas is written alongside; the PyTorch learner must match it
  numerically (gate C1) and the training driver is exercised locally with the numpy learner.
* Each Colab run prints the SHA-256 of the code bundle it ran, so results are tied to code.

## Method (frozen; these are the `DQNConfig` defaults, R-L1..R-L5)

MLP 19 → 128 → 128 → dueling heads (V: 1, A: 45), ReLU, `Q = V + A − mean(A)`; Double-DQN
target (online net picks the argmax, target net evaluates); Huber loss; AdamW (lr 2.5e-4,
amsgrad, weight decay 0.01 = the library default); gradient-norm clip 10; batch 128; replay
200,000 (numpy ring buffer, own seeded RNG); γ = 0.95 per decision (D-11); learning_starts
10,000 decisions; one gradient step every 4 decisions; soft target update τ = 0.005 after every
gradient step; ε 1.0 → 0.1 linearly over the first 30% of 300,000 decisions, then 0.1; 1-step
returns, no prioritised replay (D-12). State, action, reward, transition assembly, calibration
pass and frozen normaliser are exactly those of M8 (D-9, D-32, Addendum M8). Greedy
evaluation uses a numpy forward pass from the exported weights (R-L15), ε = 0, frozen
normaliser, cold start, 10% warm-up excluded.

Variants: `dqn` (γ = 0.95) and `dqn_bandit` (γ = 0, otherwise identical; R-L13).

## Correctness gates — must pass before ANY cache result is produced or reported

| id | gate |
|---|---|
| C1 | PyTorch learner vs numpy reference on identical weights and batch: forward Q max abs diff < 1e-5; Huber loss relative diff < 1e-4; every gradient relative diff (max-norm) < 1e-3; after 5 AdamW steps from identical weights, max abs weight diff < 1e-4 |
| C2 | Probe environments 1–5 (below): every learned Q within 0.05 of its hand-computed value, for seeds 0, 1, 2 with the PyTorch learner |
| C3 | CartPole-v1, hand-written DQN, 5 seeds × 100,000 steps: mean greedy return over the last 10 evaluation episodes ≥ 300 in at least 3 of 5 seeds. (Non-gating: a Stable-Baselines3 DQN curve if installed.) This checks the learner, not the cache problem; CartPole hyper-parameters are its own and are not reused. |

If C1 or C2 fails the PyTorch code has a defect: fixing it is allowed (and logged), the gates
re-run, and no cache experiment is run in between. Hyper-parameters stay as frozen above.

Probe environments (own definitions; the MD's probe 3 reuses the same observation on both
steps, which aliases the two states, so the second observation here is distinct):
1. one observation (0), one action, reward +1, then terminal → Q = 1.
2. observation ±1 (random), one action, reward = observation → Q(±1) = ±1.
3. observation 0 then 1, one action, reward 0 then +1 (terminal) → Q(0) = γ, Q(1) = 1.
4. observation 0, two actions, reward −1 / +1 → Q = (−1, +1).
5. observation ±1, two actions, reward +1 if action = (observation > 0) else −1 → Q(+1) = (−1, +1), Q(−1) = (+1, −1).

## Development gate (only after C1–C3 pass): seeds 100–104, validation slice, paired by seed

`ΔU = U(dqn, greedy) − U(random:45)`, same simulator seed, per capacity c ∈ {1%, 5%, 25%}.
Pass at c iff mean ΔU > 0 AND the 95% paired-bootstrap CI (10,000 resamples, RNG seed 0) has
lower bound > 0 AND ΔU > 0 in at least 4 of the 5 seeds.
**Power note:** with 5 seeds this is a weaker test than M8's 10; it is what the Colab budget
allows for the gate. The evaluation-seed run uses 10.

* **PASS**: holds at 1%. **PARTIAL**: fails at 1% but holds at 5% and 25%. **FAIL**: otherwise
  → no evaluation-seed run.
* Reported alongside, NOT gating: ΔU against `tabq:qbin`, `tabq:bandit`, `place_size:p25` and
  `fixed:redis/3600s`; collapse flag (ΔU vs random < −0.05) at each capacity; the bootstrapped
  vs bandit comparison.

## Evaluation-seed run (only on PASS/PARTIAL, once)

Seeds 0–9 × capacities {1%, 5%, 25%} × {`dqn`, `dqn_bandit`} × {val, test}, arm `harsh`;
rows appended to `results/results.csv` (`policy_class = learned`, `family = dqn`), reported with
the M6-4 paired statistic, the stale delta and a two-axis dominance check (C-49).

## What this experiment can and cannot show (stated before running)

* M8 and C-48 predict that a bootstrapped learner may be noisy because `s'` is the next
  decision of an arbitrary key; `dqn_bandit` is included for exactly that reason. A DQN that
  does no better than the tabular agent or the size rule is a plausible, reportable outcome.
* The 19 features contain little TTL information beyond the three predictor features (C-46),
  so TTL skill is capped by the fit-once predictor regardless of the learner.
* Nothing here tests real traces.

## Not allowed after the development gate is read

Changing any hyper-parameter, the budget, the variants, seeds or capacities. A repaired method
needs a new addendum and fresh development seeds (110–119).
