# M4 simulator diagnostic (development evidence — NOT an experimental result)

Produced by `python scripts/sim_grid.py <l2_footprint_frac> <staleness_mode>` on 2026-10-15.

* **Data: synthetic only** (`WorkloadConfig()` defaults: 600,000 requests, 4,000 keys, 8 h,
  α = 0.99, footprint 2.73 MB). Nothing here is a real-trace result.
* One seed, no train/validation/test split, no tuning, 10% warm-up excluded. These numbers
  characterise the simulator's behaviour; they are not a comparison of methods.
* Fixed (placement, TTL) actions, normal priority. Staleness defaults: `p_inv_l1 = 0.5`,
  `d_inv_l1 = 2 s`, `p_bypass = 0.05` (placeholders, D-20). L1 = 10% of L2.

## Throughput (R-S18)

70k–285k requests/s depending on policy; `tests/test_simulator.py::test_throughput_is_logged`
checks the samples are recorded. A 600k-request pass costs 2–9 s, so ≥300k decision steps
(R-L7) are reachable by replaying the training slice several times.

## L2 = 25% of footprint, `lossy` staleness

| policy | OHR | stale % of reads | stale given hit | backend /1k | evictions /1k | expirations /1k |
|---|---:|---:|---:|---:|---:|---:|
| redis / 5 s | 0.343 | 0.00 | 0.000 | 656.5 | 0.0 | 652.9 |
| redis / 30 s | 0.575 | 0.05 | 0.001 | 424.7 | 0.0 | 413.6 |
| redis / 120 s | 0.729 | 0.19 | 0.003 | 270.6 | 0.0 | 248.5 |
| redis / 600 s | 0.814 | 0.72 | 0.009 | 186.3 | 111.8 | 41.2 |
| redis / 3600 s | 0.826 | 2.16 | 0.026 | 173.7 | 139.2 | 1.0 |
| both / 3600 s | 0.828 | 9.11 | 0.110 | 172.1 | 306.1 | 1.0 |
| random (45 actions) | 0.791 | 5.40 | 0.068 | 208.6 | 101.6 | 150.2 |

## L2 = 25%, `ttl_only` (no invalidation at all)

| policy | OHR | stale % of reads | stale given hit |
|---|---:|---:|---:|
| redis / 5 s | 0.344 | 0.07 | 0.002 |
| redis / 30 s | 0.577 | 0.75 | 0.013 |
| redis / 120 s | 0.735 | 3.19 | 0.043 |
| redis / 600 s | 0.822 | 11.49 | 0.140 |
| redis / 3600 s | 0.836 | 28.02 | 0.335 |
| local / 3600 s | 0.468 | 8.37 | 0.179 |
| random (45 actions) | 0.811 | 23.42 | 0.289 |

## L2 = 5% of footprint, `lossy`

| policy | OHR | stale % | evictions /1k | expirations /1k |
|---|---:|---:|---:|---:|
| redis / 5 s | 0.343 | 0.00 | 0.0 | 652.9 |
| redis / 30 s | 0.545 | 0.04 | 242.5 | 203.5 |
| redis / 120 s | 0.588 | 0.14 | 391.1 | 10.6 |
| redis / 3600 s | 0.594 | 1.45 | 395.3 | 0.0 |
| local / 3600 s | 0.220 | 0.02 | 778.4 | 0.0 |
| both / 3600 s | 0.594 | 1.48 | 801.3 | 0.0 |

## What this does and does not show

1. **The hit-ratio ↔ stale-read trade-off is real and monotone in TTL** (OHR 0.34 → 0.83,
   stale 0 → 2.2% under `lossy`, 0 → 28% under `ttl_only`). The fixed-TTL ladder traces a
   frontier that a learned policy would have to dominate (INV-8). No learned policy exists yet.
2. **Capacity pressure dominates TTL at small caches**: at 5% capacity every TTL ≥ 120 s gives
   OHR ≈ 0.59 because capacity evictions, not expiry, end entries. The TTL dimension only has
   room to matter at larger capacities — this is the "gains are capacity-dependent" point in
   the MD (RLCache result) appearing in the simulator.
3. **Placement is weakly motivated under the spec's reward (finding C-37).** `both` is
   Pareto-dominated by `redis` at 25% capacity (9.1% vs 2.2% stale for +0.2 pp OHR) and `local`
   is capacity-starved. The spec's latency term `exp(−L/L0)` with `L0` = backend latency gives
   L1 0.9999, L2 0.9632, backend 0.3679, so choosing L1 over L2 is worth
   `w_lat × 0.037 = 0.018` reward per hit, against a staleness cost of up to `w_stale = 3.0`.
   A learner will probably settle on `redis` almost everywhere. Whether placement carries any
   real signal is an open empirical question for M5/M6 (reward calibration, tier-ratio sweep
   {1, 5, 10, 25}%), and "gains concentrate in TTL, not placement" would be a reportable result.
4. **Placement ≠ capacity-neutral**: L1 and L2 are separate tiers with fixed sizes, so `both`
   does not take bytes from L2. "Equal total capacity" holds across policies because every
   policy sees the same two tiers.
