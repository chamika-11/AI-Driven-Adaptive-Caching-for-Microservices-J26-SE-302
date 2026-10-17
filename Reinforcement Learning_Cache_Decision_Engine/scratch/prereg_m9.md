

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
