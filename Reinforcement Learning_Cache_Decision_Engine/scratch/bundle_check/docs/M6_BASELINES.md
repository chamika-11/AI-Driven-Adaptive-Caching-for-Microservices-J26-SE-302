# M6 — non-learned baselines on the primary arm (`harsh`), synthetic workload

Generated 2026-10-15 by `scripts/run_baselines.py` → `results/results.csv` (4,260 rows =
71 policies × 2 splits × 3 capacities × evaluation seeds 0–9) and `scripts/make_f2_t2.py` →
`results/T2_harsh_cap{0.01,0.05,0.25}.{md,csv}`, `results/frontier_harsh_cap*.json`,
`results/F2_pareto_harsh.png`.

**Everything here is synthetic** (`data_source = synthetic`). No real-trace experiment has been
run (`docs/DATA_ACCESS.md`). **No learned agent exists**; these numbers are the baseline set the
agent will have to beat, produced under the protocol of `docs/PREREGISTRATION.md` (M6-1…M6-5 and
the labelled post-hoc Addendum M6-B).

Protocol recap: primary capacity L2 = 1% of unique-object footprint, L1 = 10% of L2 (secondary:
5%, 25%); test slice = last 20% of each trace, cold start, first 10% of the slice excluded;
equal total capacity for every policy; eviction = sampled-LRU (8 candidates) for all.
Statistics are mean ± sample sd over 10 evaluation seeds.

## What the primary capacity (1%) shows

T2, test split (selected-on-validation point per family, plus random and bounds; full table in
`results/T2_harsh_cap0.01.md`):

| policy | OHR | stale reads % | backend /1k | U (selection only) |
|---|---:|---:|---:|---:|
| fixed → redis/3600 s/high (val-selected) | 0.332 ± 0.011 | 0.42 ± 0.51 | 668 | 0.630 |
| stat_ttl → mean/both | 0.332 ± 0.010 | 0.39 ± 0.47 | 668 | 0.628 |
| pred_ttl → both | 0.331 ± 0.010 | 0.18 ± 0.19 | 669 | 0.628 |
| aimd → a300/b0.5 | 0.332 ± 0.011 | 0.44 ± 0.53 | 668 | 0.630 |
| random:45 | 0.346 ± 0.011 | 0.95 ± 0.98 | 654 | 0.643 |
| place_hash → 10% local (post-hoc) | 0.342 ± 0.015 | 0.60 ± 0.72 | 658 | 0.642 |
| **place_size → p25 local (post-hoc)** | **0.363 ± 0.014** | 0.77 ± 0.81 | 637 | **0.668** |
| place_freq → k5 (post-hoc) | 0.229 ± 0.047 | 0.09 ± 0.18 | 771 | 0.502 |
| *bound:* zero-stale oracle TTL (redis) | 0.331 ± 0.010 | 0.01 ± 0.01 | 669 | 0.629 |
| *bound:* Belady-TTL (unit-size objects) | 0.563 ± 0.002 | 0.00 | — | — |
| *bound:* Belady plain (unit-size, ignores writes) | 0.565 ± 0.002 | 13.71 ± 7.17 | — | — |

Paired by seed (10 seeds): `place_size:p25` − `fixed:redis/3600s` = **+3.07 pp OHR** (se 0.32 pp,
better in 10/10 seeds) at **+0.34 pp stale reads** (worse in 10/10); `random:45` −
`fixed:redis/3600s` = +1.39 pp OHR (se 0.04 pp, 10/10).

1. **At the primary capacity TTL is almost inert.** Every fixed TTL ≥ 30 s gives the same OHR to
   three decimals (0.328–0.332); only 5 s costs hit ratio (0.269). Evictions (≈ 665 per 1,000
   reads), not expiry (≈ 0), end every entry. Stale-read rates are 0.0–1.4% depending on the seed.
2. **The only lever that moves the hit ratio is placement-as-partitioning**: a rule that sends
   some objects to L1 and the rest to L2 uses the two tiers as *disjoint* capacity, which no fixed
   action can (`redis` strands L1, `both` duplicates). Size-based partitioning is best (+3.1 pp).
   This is why `random:45` beats every one of the 45 fixed actions (diagnosis on a dev seed:
   random over placements alone 0.344, over TTLs alone 0.325, over priorities alone 0.335).
3. **It is uninformed capacity use, not intelligence**: a hash split with no information at all
   already gets +1.0 pp. A learned policy's placement gain has to be measured against these
   rules, not against `fixed:redis`.
4. **Frequency-threshold placement fails here** (0.229): with L1 ≈ 4 objects the hottest keys
   thrash in L1 and are absent from L2.
5. **The Belady bounds are far away** (0.56 vs ≤ 0.36) and are loose by construction (unit-size
   objects, offline). The baselines all use a weak sampled-LRU eviction, so a large part of the
   distance is plausibly eviction/admission quality rather than TTL or placement — this was NOT
   measured (strong eviction policies — SIEVE, S3-FIFO, W-TinyLFU — are M11 and would move
   every row up).

## Secondary capacities

| L2 / footprint | best baseline by OHR (stale %) | frontier span (OHR, stale %) | zero-stale oracle-TTL bound |
|---|---|---|---|
| 5% | place_size:p25 0.633 (2.8%) | 0.279 @ 0.02% → 0.633 @ 2.8% | 0.591 @ 0.02% |
| 25% | fixed both/3600 s 0.829 (12.7%); fixed redis/3600 s 0.827 (7.7%) | 0.279 @ 0.02% → 0.829 @ 12.7% | **0.803 @ 0.02%** |

At 25% the TTL ladder is a real trade-off curve (OHR 0.50 @ 0.2% stale; 0.68 @ 0.9%; 0.79 @
2.3%; 0.83 @ 7.7%). **A zero-stale oracle TTL attains OHR 0.803 at 0.02% stale — +30.3 pp OHR
(se 0.16 pp, 10/10) over the best baseline point with comparable staleness (`fixed:redis/30s`,
0.2% stale), and −2.3 pp stale at +1.3 pp OHR against the best predictor-based baseline
(`stat_ttl:p10`).** That gap is the headroom a learned policy could capture if it can anticipate
writes; it is information-limited (the baselines see only statistics fitted on the first 30% of
the trace).

## Gate check (§9, M6)

* *Random-policy and fixed-ladder numbers recorded* — yes (`results/results.csv`, T2).
* *Oracle-TTL has zero stale reads* — **not literally met**: 0.01–0.02% (redis) and 0.05%
  (both) at 25%. Causes: a key rewritten within 5 s still gets the 5 s minimum bucket, and the
  copy lives from fetch completion (up to ~30 ms later) so it can outlive a write by up to the
  fetch latency (tens of ms). It is "near zero", and is labelled a bound, not a zero-stale policy.
* *Never beaten on hit ratio by a zero-stale policy* — no real zero-stale policy exists in the
  set; Belady-TTL (unit-size, offline) is above it at every capacity, as it must be.

## Caveats (not hedges)

* One synthetic generator family, one staleness arm (`harsh`); `lossy` and `ttl_only` arms are
  declared but not yet run.
* Stale-read rates have a between-seed sd as large as the mean (e.g. 0.0–1.4% at 1%), so
  frontier comparisons must be paired by seed; the seed-averaged figure hides this.
* The frontier is built from seed-averaged points; the pre-registered per-seed paired ΔOHR
  statistic is implemented (`report.paired_delta`) but only meaningful once an agent exists.
* The Belady numbers use a unit-size approximation with capacity = total cache bytes / mean
  object size; they bound OBJECT hit ratio only.
* IQM / stratified bootstrap (rliable), the six-capacity sweep and strong eviction baselines are M11.
