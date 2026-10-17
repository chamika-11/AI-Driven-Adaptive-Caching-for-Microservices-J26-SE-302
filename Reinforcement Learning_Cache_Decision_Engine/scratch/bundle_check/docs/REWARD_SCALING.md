# Reward scaling study (D-10 check) — criterion declared BEFORE the results

Written 2026-10-15, before `scripts/reward_scaling.py` was run for the first time.

## Question

D-10 aggregates read-level reward terms by SUMMING over the reads a decision served and then
clips to [−10, 10], with the instruction: *if more than 5% of rewards clip, revise the scaling
before training*. A hot key held for an hour can serve thousands of reads, so saturation is a
real risk: saturated rewards cannot tell a good decision from a better one.

## Data and protocol

* **Development seeds 100, 101, 102 only.** Evaluation seeds 0–9 are never used here.
* Primary staleness regime `harsh` (the pre-registered default `Config()`), per-key backend
  latency on (`backend_sigma` = 0.5), L1 = 10% of L2.
* Two capacities, because Q-7 is still open: L2 = 5% and 25% of the unique-object footprint.
* Policies for the clip-fraction table: uniform-random over 45 actions, fixed `redis/3600 s`,
  fixed `redis/30 s`.

## Pre-declared alignment criterion

1. Split each dev trace in half by request index. On the FIRST half run each of the 15
   fixed (placement × TTL, normal priority) actions and record, per closed decision, the
   pre-clip reward `r_raw`.
2. Classes = popularity tercile × volatility tercile (the `placement_signal.py` definition).
3. For each candidate transform `f` of the reward, a class-level "agent" picks, per class, the
   action with the highest **mean** `f(r_raw)` per decision (what a one-step value learner
   estimates), requiring ≥ 20 decisions for an (class, action) cell. The **sum** aggregator is
   reported as a second column.
4. Each class-level policy is run on the SECOND half and scored by the utility per read
   `U = 1.0·hit + 0.5·exp(−L/L0) − 3.0·min(1, age/ttl)` (the trace-level objective).
5. **Selection rule (fixed now):** among candidates, choose the transform with the highest mean
   out-of-sample `U` across the 6 (seed × capacity) cells, provided it (a) clips ≤ 5% of
   rewards or is bounded by construction and (b) is monotone in the number of hits for a fixed
   per-read quality (so "more hits is better" survives). Ties within one standard error go to
   the simpler transform. The literal D-10 (sum + clip 10) is retained if it is within one
   standard error of the best.

## Candidates

| id | transform of `r_raw` | rationale |
|---|---|---|
| `clip10` | `clip(r, ±10)` | D-10 literal |
| `raw` | `r` | no transform (unbounded; for reference) |
| `div10_clip` | `clip(r / 10, ±10)` | constant rescale, clip rarely binds |
| `div100_clip` | `clip(r / 100, ±10)` | stronger rescale |
| `symlog` | `sign(r)·log(1 + |r|)` | compresses the heavy tail, order-preserving |
| `per_read` | `r / (1 + H)` | mean value per served read (loses volume) |

## Not allowed after seeing results

Adding candidates, changing the criterion, changing seeds/capacities, or switching the
evaluation seeds in. A transform added later must be logged as a new decision with the reason.

---

# Addendum A — POST-HOC (written after the first run of the study)

**Disclosure: this arm was added after seeing results**, which the section above says must be
logged with its reason.

First-run findings (dev seeds 100–102, 6 cells):

* Literal D-10 (`clip10|mean`) was the second-worst reward tested: −0.047 ± 0.015 U/read vs the
  best fixed action; `div100_clip|mean` −0.0055 ± 0.0031; `raw|mean` −0.0008 ± 0.0043;
  class-level U-optimal policy +0.0058 ± 0.0033. Clip fraction of D-10 literal: 0.4–5.7%.
* **Then, measuring term magnitudes** (`scratch/parts_stats.py`): for a fixed `redis/3600`
  policy at 25% capacity, **97.7% of decisions had utilisation > 0.9** (gate < 1). The gate
  `u = 1 − max(0, util − 0.9)/0.1` therefore shrinks almost every reward and reaches 0 at a full
  cache. A cache with eviction is full in steady state, so the gate is a state-dependent
  multiplier on the whole bracket that carries no information about the action's quality.
* So the first-run alignment result confounds clipping with the gate.

**Added arm:** the same transforms applied to the reward WITHOUT the utilisation gate
(`*_ng`), computed from the stored components (`bracket − stampede`). Same seeds, capacities,
classes, aggregator and selection rule. Gate-off is a deviation from R-R3 and is therefore only
adopted if it beats the gated variant by more than one standard error, and even then it is
flagged for the owner's sign-off (C-40).

---

# Results (dev seeds 100–102 × capacity 5% / 25% = 6 cells; second run, deterministic)

## Pre-clip distribution, D-10 literal (sum aggregation, per closed decision)

| policy | L2 cap | decisions | \|r\|>10 % | p50 | p90 | p99 | max | H = 0 % | mean H |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| random-45 | 5% | 574,708 | 0.36 | −0.10 | 0.28 | 3.63 | 4,701 | 78.5 | 1.44 |
| random-45 | 25% | 285,145 | 1.98 | −0.07 | 1.00 | 20.89 | 12,499 | 64.4 | 3.84 |
| redis/3600 | 5% | 585,385 | 1.71 | −0.93 | 2.42 | 16.11 | 14,883 | 74.6 | 1.39 |
| redis/3600 | 25% | 238,355 | **5.69** | −0.91 | 6.60 | 60.96 | 13,790 | 51.2 | 4.74 |
| redis/30 | 5% | 651,870 | 3.32 | −0.94 | 2.63 | 28.10 | 168 | 69.3 | 1.18 |
| redis/30 | 25% | 605,059 | 3.81 | −1.00 | 4.19 | 31.07 | 179 | 62.1 | 1.34 |

* The D-10 trigger (> 5% clipped) fires in one cell, the long-TTL policy at 25% capacity.
* The distribution is extremely heavy-tailed: **the top 1% of decisions carry 73% (redis/3600)
  to 84% (random) of the total reward**; the maximum is ~1.5×10⁴.
* Term mix (mean |term| share, fixed redis/3600, 25%): hit 60.5%, latency 29.2%, backend
  8.6%, **stale 1.7%, memory 0.0%, stampede 0.0%**.
* 97.7% of decisions under redis/3600 are taken with utilisation > 0.9 (gate < 1).

## Alignment (second-half U/read of the class-level policy each reward would pick)

| reward | mean-aggregator ΔU vs best fixed (± SE) | sum-aggregator ΔU |
|---|---:|---:|
| (reference) class-level U-optimal | **+0.0058 ± 0.0033** | — |
| `raw` (unbounded) | −0.0008 ± 0.0043 | −0.0201 |
| `div100_clip` = clip(r/100, ±10) | **−0.0055 ± 0.0031** | −0.0275 |
| `div10_clip` | −0.0317 ± 0.0133 | −0.0993 |
| `symlog` | −0.0464 ± 0.0151 | −0.0913 |
| `clip10` (**D-10 literal**) | **−0.0469 ± 0.0152** | −0.1290 |
| `per_read` | −0.0562 ± 0.0100 | −0.0752 |
| *post-hoc, gate removed (Addendum A):* | | |
| `raw_ng` | +0.0045 ± 0.0029 | −0.0012 |
| `div100_clip_ng` | −0.0061 ± 0.0029 | −0.0191 |
| `clip10_ng` | −0.0458 ± 0.0176 | −0.1299 |
| `symlog_ng` | −0.0469 ± 0.0179 | −0.0933 |

## Reading the result

1. **Literal D-10 is rejected.** `clip10|mean` is ~3 SE below the best fixed action and > 2.7 SE
   behind `div100_clip|mean`. Clipping destroys the ordering among exactly the hot-key
   decisions that dominate return.
2. **Selection (by the rule declared above): `clip(r / 100, ±10)`** — the best *bounded*
   candidate. After scaling only 0.02–0.08% of decisions (|raw| > 1000) clip. The unbounded
   `raw|mean` scores slightly higher but passes criterion (a) only vacuously (nothing is clipped
   because nothing is bounded; values reach 1.5×10⁴), so it is not admissible for TD learning —
   this is how criterion (a) was *intended*, but the wording left the loophole and the
   interpretation was fixed after seeing results; stated here so it is not hidden.
3. **The gate does not explain the harm.** Removing it changes `clip10` by 0.001 and `div100`
   by 0.0006 (both inside one SE). R-R3 is therefore retained; `gate_enabled=False` stays as an
   ablation arm. The gate is still conceptually odd (it drives reward to 0 at a full cache, which
   is the normal steady state; the agent sees utilisation as feature #10 and can model it).
4. **No reward, however scaled, makes a class-level agent clearly beat the best fixed action
   out of sample**, and the U-optimal class policy itself is only +0.0058 ± 0.0033 (~0.5%).
   Under `harsh` at class granularity (3 × 3 terciles) the headroom above the best single fixed
   action is small. A DQN with continuous features can use more information than 9 classes, but
   this sets an honest expectation: **margins over the best fixed (TTL, placement) action are
   likely to be fractions of a percent of utility; the headline claim will be about the
   (hit ratio, stale-read) frontier, and a null/small result is plausible.**
5. **The memory term is inert** with the spec's normalisation (`byte_seconds / (capacity ×
   3600 s)`; mean contribution < 10⁻⁴). `w_mem` sweeps are meaningless until the normalisation
   changes (open item C-39).

Caveats: class-level tabular means are a proxy for a DQN's behaviour, not a DQN; synthetic data;
6 cells; SEs are over those cells.
