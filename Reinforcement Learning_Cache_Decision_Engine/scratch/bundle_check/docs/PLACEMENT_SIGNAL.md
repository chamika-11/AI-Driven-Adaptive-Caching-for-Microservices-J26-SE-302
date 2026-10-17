# C-37 investigation: does the placement dimension carry signal?

Run 2026-10-15 with `scripts/placement_signal.py` (`scan`, `classes`, `oracle`).
**Synthetic data only; 3 workload seeds; one simulator seed. Nothing here is a real-trace result
and no learned agent exists yet** — this measures how much value *any* state-dependent rule could
extract, which bounds what a DQN can learn.

## Method

* Utility per read, from the spec's read-level reward terms
  `U = 1.0·1{hit} + 0.5·exp(−L/L0) − 3.0·min(1, stale_age/ttl)` (backend and memory terms are
  monotone in hits and omitted). All numbers are `U` per read; a typical level is 1.0–1.3.
* **`scan`**: fixed placement × TTL 600 s across 16 regimes (capacity, tier ratio, staleness,
  `L0`).
* **`classes`** (out of sample): classes = popularity tercile × volatility tercile (+ "unseen"),
  computed from the FIRST half of the trace. For each class the best action is chosen from 15
  fixed (TTL × placement, normal priority) runs on the first half, then the resulting rule is
  **run on the second half**. Compared with the best single fixed action. Variants: TTL varies
  per class (placement fixed), placement varies per class (TTL fixed), both; plus per-key
  versions (identity-based, prone to overfitting).
* **`oracle`**: rules that use the future (time to the key's next write): a *zero-stale TTL*
  (largest bucket ≤ time-to-next-write) and a *volatility-aware placement* (`both` unless a
  write lands inside the TTL, then `redis`). **These are not upper bounds on U** — zero staleness
  is not utility-optimal under a finite staleness penalty, and the zero-stale TTL is often worse
  than the best fixed TTL. They show how much a perfectly informed *simple* rule could add.

## 1. Fixed placements (`scan`, TTL 600 s, mean of 3 seeds)

| regime | U redis | ΔU both−redis (±sd) | ΔU local−redis (±sd) | best |
|---|---:|---:|---:|---|
| cap 5%, L1 5%, lossy, **L0 = 8 ms (spec)** | 0.959 | +0.0002 ± 0.0005 | −0.565 ± 0.021 | both |
| cap 5%, L1 25%, lossy, L0 = 8 ms | 0.959 | −0.0110 ± 0.0185 | −0.299 ± 0.011 | redis |
| cap 25%, L1 5%, lossy, L0 = 8 ms | 1.237 | −0.0163 ± 0.0168 | −0.578 ± 0.006 | redis |
| cap 25%, L1 25%, lossy, L0 = 8 ms | 1.237 | −0.0276 ± 0.0148 | −0.246 ± 0.004 | redis |
| cap 25%, L1 25%, **instant L1 invalidation**, L0 = 8 ms | 1.243 | +0.0103 ± 0.0003 | −0.212 ± 0.013 | both |
| cap 25%, L1 25%, lossy, **L0 = 300 µs** | 0.961 | +0.1400 ± 0.0130 | −0.035 ± 0.005 | both |
| cap 25%, L1 25%, instant L1 inval., L0 = 300 µs | 0.966 | +0.1782 ± 0.0025 | −0.002 ± 0.015 | both |

(full 16-regime scan: `scratch/placement_scan.json`, not committed.)

* **`local` never wins.** Best case is a tie (L1 = 25% of L2, reliable invalidation, L0 = 300 µs).
* **Under the spec's own constants (`L0` = backend latency) `both` ≈ `redis`**: identical hit
  ratio (0.600/0.600, 0.816/0.817) and a difference of −0.03…+0.01.
* **The only large placement effect comes from changing `L0` to the tier scale** (+0.14…+0.18)
  — i.e. from changing the objective, not from the cache's behaviour.
* Structural cap from the spec's constants: choosing L1 over L2 is worth at most
  `w_lat·(e^{−1/8000} − e^{−300/8000})·OHR ≈ 0.0183 × 0.83 ≈ 0.015` U/read (≈ 1.2%), reached only
  if every hit came from L1.

## 2. State-dependent rules, scored on the second half (3 workload seeds; ΔU vs best single fixed action)

| regime | class TTL-only | class place-only | class joint | **place on top of TTL** (±sd) | key TTL-only | key place-only | zero-stale TTL (future) | volatility place (future) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| default (cap 25%, lossy, L0 = 8 ms) | +0.0012 | +0.0028 | +0.0036 | +0.0024 ± 0.0015 | −0.0033 | −0.0103 | −0.0130 | +0.0053 |
| cap 5% | −0.0020 | +0.0052 | −0.0016 | +0.0004 ± 0.0025 | +0.0001 | −0.0010 | −0.0035 | −0.0001 |
| L1 = 25% of L2 | +0.0012 | +0.0035 | +0.0011 | −0.0001 ± 0.0062 | −0.0033 | −0.0065 | −0.0130 | +0.0087 |
| L1 = 25%, L0 = 300 µs | +0.0041 | +0.0000 | +0.0041 | +0.0000 ± 0.0000 | +0.0232 | +0.0030 | +0.0252 | +0.0020 |
| Zipf α = 1.2 | +0.0017 | +0.0023 | +0.0041 | +0.0024 ± 0.0044 | −0.0017 | −0.0148 | n/a | n/a |
| "friendly" (cap 5%, L1 25%, instant inval., L0 = 300 µs) | +0.0018 | +0.0000 | +0.0018 | +0.0000 ± 0.0000 | +0.0066 | +0.0103 | −0.0110 | −0.0029 |
| **harsh** (p_inv 0.2, d 10 s, p_bypass 0.3) | +0.0272 | −0.0013 | +0.0289 | +0.0017 ± 0.0009 | +0.0142 | −0.0262 | +0.0176 | +0.0064 |
| **ttl_only** (no invalidation at all) | +0.0636 | +0.0010 | +0.0642 | +0.0005 ± 0.0009 | +0.0874 | +0.0077 | +0.1143 | −0.0049 |

## Findings

1. **Placement signal exists in the model but is small: ≈ 0.000 to +0.009 U/read (≤ 0.7% of U)
   even with future knowledge** (volatility-aware placement: +0.005 default, +0.009 at a 25% L1,
   +0.006 harsh, ≈ 0 or negative elsewhere). Out of sample, class-level placement adds
   +0.000…+0.0024 on top of per-class TTL. At n = 3 workload seeds these are within one to two
   standard deviations of zero in most regimes; only the `harsh` and `default` increments have
   a standard deviation smaller than the mean, and both are < 0.003.
2. **Identity-level (per-key) placement is harmful out of sample** (−0.010…−0.026 in lossy
   regimes): the first half's per-key preference does not transfer. Whatever placement signal
   exists is coarse (volatile vs stable keys), not key-specific.
3. **`local` is a dominated action under every tested configuration**, so effectively the
   learnable placement choice is `redis` vs `both`.
4. **TTL signal is the real yardstick, and it depends entirely on how reliable invalidation is.**
   With reliable L2 invalidation (the default `lossy` model) per-class TTL adds only
   +0.001…+0.004 — a long TTL is nearly free, exactly the "TTL = ∞ + invalidation dominates"
   risk noted in C-6. With unreliable invalidation (`harsh`) it adds +0.027; with none
   (`ttl_only`) +0.064 (class) to +0.087 (per key), and the zero-stale TTL +0.114. Placement's
   gain stays ≤ 0.003 in all of them: **placement is 1–2 orders of magnitude below TTL where TTL
   matters, and the two are comparably tiny where TTL does not.**
5. **Consequence for the research claim.** The joint-action claim (INV-8) is only testable in
   regimes where staleness has teeth. In this model the gain comes from TTL; "gains concentrate
   in TTL, not placement or priority" is the likely reportable outcome. This is not a bug in
   the simulator: it follows from (i) the spec's `L0` choice and (ii) the L2-synchronous /
   L1-lossy invalidation assumption, which is the *only* mechanism that makes placement matter
   for staleness (D-20 placeholders).

## Caveats

* 3 workload seeds, 1 simulator seed, synthetic workloads from one generator family; the
  standard deviations are small-sample.
* One L1 (a single sidecar). With one sidecar per client/service instance (A-7) a local copy is
  duplicated per instance and sees only that instance's traffic — a materially different
  placement problem that this simulator does not model and that could change the conclusion.
* Utility omits the memory and backend terms; with `w_mem` > 0 `both` is penalised further.
* The staleness parameters are placeholders (D-20); the finding "placement helps only through
  differential invalidation reliability" would flip if L1 invalidation were as reliable as L2
  *and* `L0` stayed at 8 ms (then `both` ≥ `redis` by +0.005…+0.010 from latency alone).
