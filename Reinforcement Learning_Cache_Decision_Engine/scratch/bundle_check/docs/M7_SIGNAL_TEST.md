# M7 — agent-free signal test (pre-registered: `docs/PREREGISTRATION.md`, Addendum M7)

Run 2026-10-15 with `scripts/signal_test.py` on **development seeds 100–109** (evaluation seeds
0–9 untouched), arm `harsh`, test slice with 10% warm-up excluded. Synthetic data only; no
learned agent involved. Raw rows: `results/signal_test.csv`, summary `results/signal_test.json`.

## Outcome under the pre-registered decision rule: **PARTIAL**

| capacity | mean Δstale (pp) | 95% paired CI (pp) | seeds > 0 | rel. reduction | ΔOHR | G1 | G2 | G3 | G4 | pass | Spearman(acc, stale) |
|---|---:|---|---:|---:|---:|:-:|:-:|:-:|:-:|:-:|---:|
| **1% (primary)** | 0.012 | [−0.006, +0.033] | 8/10 | 0.221 | +0.0005 | **✗** | ✓ | ✓ | ✓ | **✗** | 0.00 |
| 5% | 1.523 | [+0.734, +2.553] | 9/10 | 0.471 | +0.0025 | ✓ | ✓ | ✓ | ✓ | ✓ | −1.00 |
| 25% | 2.964 | [+1.948, +4.179] | 10/10 | 0.479 | +0.0078 | ✓ | ✓ | ✓ | ✓ | ✓ | −1.00 |

Δstale = stale(accuracy 0) − stale(accuracy 1), paired by seed. `interpolate` mode gives identical
numbers (the policy's decisions depend only on the bucket the predicted TTL falls in).

Seed-mean stale-read rate (%) by predictor accuracy (mixture):

| capacity | a = 0 | 0.25 | 0.5 | 0.75 | 1.0 |
|---|---:|---:|---:|---:|---:|
| 1% | 0.091 | 0.072 | 0.083 | 0.138 | 0.079 |
| 5% | 2.859 | 1.908 | 1.831 | 1.577 | 1.336 |
| 25% | 5.974 | 4.652 | 4.437 | 3.523 | 3.010 |

## What this does and does not say

* **The predictor stand-in carries clear, graded TTL signal where TTL has room** (5%, 25%): the
  accurate predictor roughly halves the stale-read rate at no hit-ratio cost, with a monotone
  dose-response. The "cheat-agent" check the MD asks for passes there.
* **At the primary capacity it does not clear the pre-registered bar.** G1 fails: the effect
  (0.012 pp of reads) is inside seed noise. G3 passed only marginally and is sensitive to seeds
  whose a = 0 baseline is near zero. This is consistent with C-41 (TTL is nearly inert at 1%: the
  stale-read rate is ~0.1% for every accuracy). Per the rule, the write-up MUST state that the
  primary endpoint has no usable TTL-prediction signal and that the 5% / 25% arms are the
  evidence for any TTL claim.
* **Not a go-ahead for any claim about a learned agent.** This tests a heuristic fed the
  predictor feature; it shows the input is informative, not that an agent can use it better.

## Secondary diagnostic (non-gating): do the 19 observations predict the ideal TTL?

Held-out R² of a 64-64 ReLU MLP regressing `log1p(min(time to next write, 3600 s))` on the
observation at every decision of a `random:45` run (train slice → test slice):

| seed | cap | n_train | n_test | R² (a = 1.0) | R² (a = 0.0) | R² (predictor features zeroed) | ΔR² (1.0 − 0.0) |
|---|---:|---:|---:|---:|---:|---:|---:|
| 100 | 1% | 124,622 | 49,593 | 0.455 | 0.020 | 0.006 | 0.435 |
| 100 | 25% | 37,815 | 18,671 | 0.522 | 0.079 | 0.022 | 0.443 |
| 101 | 1% | 130,258 | 54,125 | 0.436 | 0.038 | 0.015 | 0.398 |
| 101 | 25% | 38,802 | 19,797 | 0.519 | 0.118 | 0.126 | 0.401 |
| 102 | 1% | 141,392 | 60,256 | 0.498 | 0.163 | 0.090 | 0.335 |
| 102 | 25% | 41,037 | 20,961 | 0.507 | 0.117 | 0.090 | 0.390 |

* **Supportive by the pre-registered threshold** (ΔR² ≥ 0.05; observed 0.34–0.44).
* **The observation carries real information about the ideal TTL (R² ≈ 0.45–0.52), and nearly
  all of it comes from the three predictor features** (#9 predicted TTL, #10 volatility, #19 hot
  flag). With them zeroed, the other 16 features explain 0.6–12.6% of the variance. The cache
  and recency/frequency features are almost uninformative about time-to-next-write: the 19
  features contain no direct "time since this key was last WRITTEN" signal. A learned agent's TTL
  skill will therefore be bounded by the quality of the frozen, fitted-once predictor (INV-1
  fixes the feature set, so this is a design observation, not something to patch silently).
* This diagnostic was run on 3 dev seeds at 1% and 25% (the pre-registration did not fix the
  capacity; 25% is an addition, labelled here).

## Deviations and environment

* **PyTorch is blocked on this machine** by a Windows Application Control policy
  (`WinError 4551`, loading `torch_python.dll`; it imported at install time on 2026-10-14 and
  not afterwards). The diagnostic therefore uses a pure-numpy 64-64 MLP (Adam, minibatch 512,
  8 epochs). The pre-registration specified the architecture, not the framework. No attempt was
  made to bypass the policy. **M9 (the DQN) is blocked by this** — see C-47.
* Seeds with a(=0) stale rate of exactly 0 would be excluded from G3; none occurred.
