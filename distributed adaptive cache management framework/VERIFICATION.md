# Verification recorded 8 October 2026

The original `Pseudocode/` files were preserved. Go modules are pinned in `go.mod` and `go.sum`. These checks exercised the implementation in this workspace.

## Executed checks

| Check | Result |
|---|---|
| `gofmt -l cmd internal` | Clean; no filenames returned |
| Host `go test ./...` | Passed; real-dependency tests require environment variables |
| Host `go vet ./...` | Passed |
| Host `go test -race ./...` | Could not run: CGo/C compiler unavailable |
| `docker compose run --rm verify` | Passed `go vet ./...` and `go test -race -count=1 -v ./...` |
| Container tests | All 15 passed, including real Redis and PostgreSQL tests; no race reports |
| Docker build | All seven Go binaries built successfully |
| Executable smoke | Miss, hit, batch creation, workflow invocation, policy application and later expiry all passed |
| AI-container outage | Eight successful product requests while AI stopped; an AI failure was observed in sidecar metrics; AI restarted |

The suite includes concurrent fill/policy changes, Redis compare-and-set preservation, expiry preservation, default/learned/expired policies, null values, correct event counts, timer/size flushing, queue saturation, invalid and out-of-order decisions, sidecar/AI failures, singleflight, shutdown cancellation, and lookups completing while inference is blocked.

Evidence: [race and integration output](evidence/race-and-integration.txt), [smoke output](evidence/smoke-success.txt), [outage output](evidence/smoke-ai-outage.txt).

## Small three-mode benchmark

Executed `scripts/benchmark.ps1 -Duration 10s -Rate 100 -Keys 1000`: stable hot-key scenario, seed 42, 1,024-byte seeded payload, 32 generator workers. Each mode used the same Compose infrastructure and cold caches. No invalidation. These are individual smoke trials, not statistically controlled performance conclusions.

| Mode | Requests | HTTP errors | Achieved RPS | p95 ms | Application DB reads | Hit rate | Applied policies |
|---|---:|---:|---:|---:|---:|---:|---:|
| No cache | 1000 | 0 | 100.08 | 2.066 | 999 | 0% | 0 |
| Fixed TTL | 1000 | 0 | 100.07 | 4.332 | 102 | 89.8% | 0 |
| Mock adaptive TTL | 1000 | 0 | 100.06 | 3.909 | 102 | 89.8% | 189 |

All three had zero generator drops, zero dropped analysis batches, zero AI failures and 1,000 matching-version freshness validations. The no-cache DB read count can be below request count because per-instance singleflight remains enabled in every mode. Requested load is 100 RPS; achieved RPS includes drain and can differ slightly from the nominal duration.

The no-cache p95 was lower in this local trial. Cached modes reduced DB reads but added sidecar HTTP overhead. These measurements do not establish a latency advantage, AI effectiveness, or distributed capacity.

Raw metrics and results: [none](evidence/none-hot.json), [fixed](evidence/fixed-hot.json), [adaptive](evidence/adaptive-hot.json). Request-level JSONL samples remain in `results/`.

## Update-heavy trial

Executed `scripts/benchmark.ps1 -Modes adaptive -Scenarios updates -Duration 5s -Rate 50 -Keys 100 -Payload 256 -UpdateRate 100` with invalidation disabled:

- 250 successful product responses, zero HTTP errors, 26 application DB reads, 89.6% hit rate.
- 482 successful database updates; the updater reported one error. The counter does not retain its exact cause, so it is not claimed as a clean updater run.
- 20 policy updates and zero AI failures.
- Separate validation: 250 DB reads, 6 matching/fresh responses, 36 provably stale responses, 208 indeterminate responses, zero validation errors.
- Reported stale rate is 36/42 = 85.7% **among classifiable responses only**, not among all 250 responses. Most responses cannot be classified from the final database snapshot because further updates happened afterward.

Raw result: [update workload](evidence/adaptive-updates.json). The standard 1,000-product, 1,024-byte dataset is restored after this trial.

## Runtime and scope

Docker initially returned an engine error and later recovered. Port 8080 was occupied, so `.env` sets `APP_PORT=18080`; no existing listener was stopped. The normal adaptive configuration runs at `http://localhost:18080/products/1`, with 60-second default TTL. PostgreSQL, Redis, workflow, sidecar, app and Prometheus remain available through Compose.

The race check was verified in Linux containers, not with Windows CGo. HTTP benchmarking exercised the hot and updates scenarios; the seeded selection test covers all six implemented scenarios, but the other four were not load-tested here. The optional second app/sidecar pair was not started. No trained models or distributed performance claims were evaluated. Before/after resource and queue snapshots are in the JSON; they are not peak measurements. See the README for multi-instance coherence, clock, validation and shutdown limitations.
