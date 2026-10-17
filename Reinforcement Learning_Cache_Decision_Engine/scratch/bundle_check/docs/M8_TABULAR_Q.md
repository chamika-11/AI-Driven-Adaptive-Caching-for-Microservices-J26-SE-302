# M8 — tabular Q-learning (pre-registered: `docs/PREREGISTRATION.md`, Addendum M8 + M8-a)

Agent: 1024 states (5 features × 4 bins) × 45 actions, α = 0.1, γ = 0.95 per decision,
ε 1.0 → 0.1 over the first 30% of 300,000 training decisions, greedy evaluation with a
visit-weighted fallback. numpy only (PyTorch is blocked on this machine, C-47).
Synthetic data only; no real-trace result exists.

## Development gate (dev seeds 100–109, validation slice, paired by seed) — outcome **PASS**

Gate: U(tabq:qbin) − U(random:45), `harsh` arm. Rows: `results/tabq_dev.csv`.

| capacity | mean ΔU | 95% paired CI | seeds > 0 | pre-registered result |
|---|---:|---|---:|---|
| **1% (primary)** | +0.0179 | [+0.0141, +0.0218] | 10/10 | **pass** |
| 5% | +0.0131 | [+0.0044, +0.0259] | 9/10 | pass |
| 25% | **−0.2430** | [−0.4042, −0.0721] | 4/10 | **fail** |

By the rule fixed in advance ("PASS iff it holds at the primary capacity") the gate is PASS.
**The 25% failure is a real result, not noise**: the γ = 0.95 agent has a hit ratio of 0.554
against 0.764 for uniformly random actions.

Context (validation slice, seed means; U / OHR / stale %):

| capacity | tabq:qbin | tabq:ewidth (MD-literal bins) | tabq:bandit (γ = 0) | random:45 | fixed redis/3600 | place_size:p25 (post-hoc) |
|---|---|---|---|---|---|---|
| 1% | 0.649 / 0.347 / 0.40 | 0.610 / 0.316 / 0.12 | 0.650 / 0.347 / 0.20 | 0.631 / 0.333 / 0.39 | 0.614 / 0.320 / 0.15 | **0.651 / 0.352 / 0.72** |
| 5% | 0.955 / 0.595 / 2.28 | 0.929 / 0.573 / 1.90 | 0.949 / 0.589 / 1.69 | 0.942 / 0.589 / 2.52 | 0.944 / 0.586 / 2.18 | **0.985 / 0.622 / 2.27** |
| 25% | 0.885 / 0.554 / 4.25 | 1.107 / 0.766 / 9.66 | 1.175 / 0.800 / 7.76 | 1.128 / 0.764 / 7.00 | **1.225 / 0.825 / 5.64** | 1.200 / 0.804 / 3.74 |

What the table says, without dressing it up:

* **The tabular agent clears the low "beats random" bar at 1% and 5%, but it does not beat the
  hand-written placement rule** (`place_size:p25`: 0.651 vs 0.649 at 1%; 0.985 vs 0.955 at 5%) nor
  the best fixed action at 25%. A learned table that roughly ties a one-line size threshold is
  the honest summary.
* **MD-literal equal-width bins (`ewidth`) are worse than equal-frequency bins at 1% and 5%**,
  as predicted (the features sit in the lowest bin). They look better at 25%, where `qbin`
  collapses — which is a statement about `qbin` failing there, not about equal-width bins being good.
* **γ = 0 (bandit) matches γ = 0.95 at 1%** (0.650 vs 0.649), is slightly worse at 5% (0.949 vs
  0.955), and is **far better at 25%** (1.175 vs 0.885). The sequential formulation does not
  earn its keep in this simulator at the tabular level — the MD's own "the problem may not be
  meaningfully sequential" outcome.

## Why the 25% run collapses (diagnosis on dev seed 105; hypothesis, not a controlled test)

* Across seeds the outcome is **bimodal**: 4 seeds reach U ≈ 1.17–1.21 (about the best fixed
  action), 6 collapse to U 0.57–0.84 (OHR 0.28–0.49). The collapsed policies choose `local`
  placement for ~47% of decisions, which at 25% capacity is a bad action (L1 is 2.5% of the footprint).
* With γ = 0.95 the table's values are ~20× larger than the bandit's (median 0.18 vs ≈ 0.00;
  p99 2.3 vs 0.28). The continuation term `γ·max Q(s')` is almost action-independent here — the
  next decision belongs to an arbitrary other key — so it adds noise to every cell that swamps
  the action-dependent reward differences (≈ 0.01–0.1). Only 8% of states are visited and the
  median tried cell has ~9 updates, so argmax over such cells follows noise.
* This is the semi-MDP credit-assignment weakness of the design (D-9: `s'` is the next decision's
  state, not the same key's next state). **A function-approximation agent will face the same
  structural problem**; it is not a tabular artefact.
* The pre-registration forbids changing α, γ, ε, bins or budget after the gate was read. Any
  repair (e.g. a different successor-state definition, shorter horizon, reward normalisation)
  needs a new addendum and fresh development seeds (110–119).

## State coverage (R-L12)

At 300,000 decisions: 31% of the 1,024 states are visited at 1% capacity, 10% at 25% (seed 100),
8% for the collapsing seed 105; only ~2,800 of 46,080 (state, action) cells were ever tried. The
coverage figure is produced after the evaluation-seed run (below).

---

# Evaluation-seed run (seeds 0–9, test slice, once) — appended 2026-10-15

180 rows appended to `results/results.csv` (`policy_class = learned`, `family = tabular_q`),
configuration exactly as pre-registered (no tuning after the development gate). Paired by seed,
10 seeds, bootstrap 95% CI of the paired mean (10,000 resamples). Full numbers:
`results/tabq_eval_summary.json`, tables `results/T2_harsh_cap*.md`, figure `results/F2_pareto_harsh.png`
(learned agents are gold stars; they never enter the frontier).

## Pre-registered statistic: ΔOHR against the concave envelope of the non-bound heuristics

| capacity | tabq:qbin | tabq:ewidth | tabq:bandit (γ = 0) |
|---|---|---|---|
| **1% (primary)** | **+0.67 pp** [+0.22, +1.16], above envelope 8/10 | −1.21 pp [−2.66, +0.40], 2/10 | +0.49 pp [+0.09, +0.79], 8/10 |
| 5% | −2.28 pp [−2.82, −1.64], 0/10 | −2.68 pp [−4.27, −1.54], 0/10 | −2.52 pp [−3.17, −1.80], 0/10 |
| 25% | **−18.74 pp** [−28.40, −9.06], 1/10 | −4.60 pp [−8.86, −1.46], 1/10 | −0.14 pp [−0.36, +0.04], 3/10 |

**Caveat that must travel with this table.** The envelope is extended flat to the right of the
most-stale baseline, so ΔOHR > 0 is NOT Pareto dominance when the agent has more staleness than
the points it is compared with. At 1%, `tabq:qbin` has +0.17 pp more stale reads than
`place_size:p25`. No learned policy dominates any baseline frontier point in both axes.

## Head-to-head (test slice; ΔU, CI, seeds where the agent is better)

| capacity | agent | vs `random:45` | vs `fixed:redis/3600s` | vs `place_size:p25` (post-hoc rule) |
|---|---|---|---|---|
| 1% | qbin | +0.0263 [+0.021, +0.032] 10/10 | +0.0393 [+0.034, +0.045] 10/10 | **+0.0017 [−0.006, +0.009] 5/10 (tie)** |
| 1% | bandit | +0.0185 [+0.015, +0.022] 10/10 | +0.0314 [+0.028, +0.035] 10/10 | −0.0062 [−0.016, +0.002] 4/10 |
| 5% | qbin | +0.0206 [−0.005, +0.050] 7/10 | +0.0062 [−0.012, +0.028] 6/10 | −0.0440 [−0.061, −0.027] 1/10 |
| 5% | bandit | +0.0121 [−0.001, +0.027] 8/10 | −0.0023 [−0.009, +0.004] 6/10 | −0.0524 [−0.073, −0.035] 0/10 |
| 25% | qbin | −0.1936 [−0.330, −0.058] 4/10 | −0.3057 [−0.433, −0.181] 0/10 | −0.2913 [−0.427, −0.160] 0/10 |
| 25% | bandit | +0.0800 [+0.055, +0.108] 10/10 | −0.0321 [−0.051, −0.014] 1/10 | −0.0177 [−0.036, −0.001] 3/10 |

## Reading it

1. **The evaluation seeds confirm the development gate**: both bootstrapped variants clear random
   at 1% (10/10 seeds); `qbin` (γ = 0.95) collapses at 25%, as on the dev seeds (−0.19 U, −17.7 pp OHR).
2. **At the primary capacity the learned table ties a one-line size threshold** (U +0.0017, CI
   spans zero) — it has rediscovered capacity partitioning and no more. It beats uninformed
   baselines clearly and the fixed ladder by +0.039 U.
3. **At 5% and 25% it does not beat the simple rules**; at 5% it is below the baseline envelope
   in 10/10 seeds. The bandit arm is the safer learner (never catastrophic) and equals or beats
   γ = 0.95 at 1%/25%, so there is no evidence here that bootstrapping helps.
4. **The MD-literal equal-width bins are worse** (−1.2 pp at 1%, −2.7 pp at 5%), and the
   coverage figure shows why: 44 of 1,024 states visited at 1%, the top 10 holding 99.7% of
   updates (`results/F_tabq_coverage.png`; equal-frequency bins reach 322 states).
5. **INV-8 is not supported by this agent**: the tabular learner does not Pareto-dominate the
   baseline frontier at any capacity. That is the expected tabular outcome per the MD; the
   function-approximation agent (M9) has not been run and cannot be on this machine today (C-47).
