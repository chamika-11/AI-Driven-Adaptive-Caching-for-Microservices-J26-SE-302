# Asynchronous adaptive cache prototype

Runnable Go research prototype based on `Pseudocode/`. The main service never calls the AI workflow. Mock LSTM/RL components are deterministic engineering placeholders: **these experiments do not demonstrate trained-model or AI performance**.

Executed checks and smoke measurements are recorded in [VERIFICATION.md](VERIFICATION.md), with raw evidence in `evidence/`.

For a beginner walkthrough and a presentation script, start with [demo guide.md](demo%20guide.md). Grafana is provisioned at [localhost:13000](http://localhost:13000) with request-path and background-AI dashboards; no manual dashboard import is needed.

For the implementation walkthrough, read [code explanation.md](code%20explanation.md): startup order, a complete product request, background batching, the mock TTL calculation, Redis safeguards, concurrency and how the code produces dashboard metrics.

## Run

Requires Docker Desktop with Linux containers and Docker Compose v2. Local Go commands require Go 1.26+; the container build pins Go 1.27.1. Ports 5432, 6379, 8080–8082 and 9090 must be available.

If port 8080 is occupied, set `APP_PORT=18080` in `.env` and use `http://localhost:18080` for host requests. Internal container URLs stay unchanged. This workspace's local `.env` uses 18080 to avoid an existing listener.

```sh
docker compose up -d --build
docker compose run --rm tools -mode seed -keys 1000 -payload 1024
curl http://localhost:8080/products/1
curl http://localhost:8080/readyz
```

Initial PostgreSQL volume creation runs `migrations/001_products.sql`, including 1,000 sample products. The seed command is idempotent in key count, updates payloads and increments existing versions. Migrations do not automatically rerun on an existing database volume. Application readiness depends on PostgreSQL; sidecar readiness depends on Redis. AI downtime does not make the application unready.

```sh
docker compose logs app sidecar workflow
docker compose down
```

`down` preserves database data. Services run as an unprivileged user in the application image. Default database credentials are for this local prototype. Services have no authentication and must not be publicly exposed.

## Layout and flow

| Path | Purpose |
|---|---|
| `cmd/app` | Product HTTP service, PostgreSQL reads, per-instance singleflight |
| `cmd/sidecar` | Local/Redis cache API and background pipeline |
| `cmd/workflow` | `/analyze`, mock predictor and policy agent |
| `cmd/data` | Seed and independently scheduled database updates |
| `cmd/load` | Seeded open-loop load generator and JSON results |
| `cmd/validate` | Separate version-aware freshness validation |
| `cmd/smoke` | Executable assertions for the end-to-end flow |
| `internal/system` | Contracts, cache, queue, workflow, metrics, HTTP/DB adapters |
| `internal/bench` | Traffic, metrics collection and freshness classification |

```mermaid
flowchart LR
  U[Client] --> A[Main application]
  A --> S[Sidecar]
  S --> L[Bounded local LRU]
  L -->|miss| R[Shared Redis]
  S -->|miss or failure| A
  A -->|miss| D[PostgreSQL]
  A -->|bounded awaited insertion| S
  S --> B[Access aggregation]
  B --> Q[Bounded analysis queue]
  Q --> W[Background workers]
  W --> F[Workflow /analyze]
  F --> P[Mock LSTM]
  P --> RL[Mock RL with original context]
  RL --> W
  W --> T[Validated TTL policies]
  T --> S
```

Requests try local cache, then Redis, then PostgreSQL. Every valid lookup records exactly one access, even when Redis fails. Fills have separate observations and counters. The main service awaits insertion for up to `CACHE_TIMEOUT`; **insertion adds request latency**. AI inference, retries and analysis are entirely outside this path.

Singleflight combines overlapping database fetches for one key within one application instance. Each caller still performs one sidecar lookup. A shared fetch has a bounded independent context so cancellation of its initiating caller does not abort other waiters. It runs within an HTTP handler and drains with that handler. Singleflight is not a distributed lock and does not combine requests across instances.

## Cache correctness

Entries carry JSON value (including valid `null` or empty values), source version, original `fetchedAt`, and absolute `expiresAt`. Main uses DB-query start as `fetchedAt`, conservatively including database time in freshness age. Redis promotion preserves expiry. Learned policies apply to insertion; missing/expired policies use the default.

Policy updates compute `fetchedAt + ttlSeconds`, capped by maximum freshness age, and evict if already expired. They do not read PostgreSQL or recreate absent entries. Local operations use a mutex. Redis expiry changes compare the entire prior entry in Lua before modifying it; a concurrent fill wins. Redis insertion rejects an older source version. A failed Redis update preserves the previous policy. Responses are validated in full before any decision is applied; a subsequent Redis failure can produce a partial application across keys, counted and logged.

Local cache, policies and last-fill observations are bounded LRUs. Histories keep eight immutable windows per configured endpoint. Active access buffers are bounded by batch size; the endpoint allowlist is capped at 32. Queue overflow drops the incoming batch and increments `batch_dropped`; history still records that observation window. Each entry is bounded by the body limit, so the local worst-case payload bound is approximately `LOCAL_CAPACITY × BODY_LIMIT` plus metadata.

Policy ordering uses increasing endpoint sequences. Concurrent AI calls are allowed; a result older than the latest accepted sequence is rejected. Applying decisions is serialized. Locks used for metrics buffers never cover network calls. Cache operations use a separate lock, including short Redis operations, so Redis latency can cause local lock contention; the main service's HTTP timeout bounds its wait.

## Background workflow

Flush after 100 accesses per endpoint or every 5 seconds. RPS uses the actual window length (a 1 ms denominator floor prevents unstable division in tiny windows). Workers attach bounded historical aggregates, current policies, observed fills, local capacity/usage, Go heap bytes and queue depth. Redis memory and CPU utilization are explicitly `null` when unavailable. A first fill does not invent an update rate. When two observed source versions differ, the fill interval divided by version delta is reported as an **observed estimate**, not exact database update timing.

Mock LSTM computes a weighted historical/current per-key request rate. Mock RL uses default TTL until two historical windows exist; then `minTTL + floor(15 × log(1 + predictedRate))`, optionally shortened to half the observed update interval, clamped to configured bounds. The sidecar calls only `/analyze`. `Predictor` and `PolicyAgent` in `workflow.go` are the replacement points for real model adapters; keep the versioned contract and decision validation when replacing them.

Each AI attempt has a timeout. Retries use bounded exponential backoff starting at 50 ms. Invalid job IDs/schema, unknown/duplicate keys, fractional/nonfinite/out-of-range TTLs and stale sequences are rejected. Previous/default policies remain usable on AI failures. Fill observations are sampled as the latest per key, not an unbounded event log.

Shutdown first stops HTTP acceptance and drains handlers, stops background timers, flushes partial windows using the same nonblocking overflow rule, closes the queue and drains workers within the remaining deadline. It then cancels calls and closes database/Redis clients. If the queue is full, the final partial batch can be dropped. No background goroutine is created per event.

## API

All structured cache operations use JSON POST bodies; TTLs are integer seconds and timestamps are RFC3339 UTC. Unknown fields, oversized bodies and invalid identities are rejected. Endpoint identities must be in `ENDPOINTS`; keys are 1–256 bytes. `sourceVersion` is a nonnegative integer (use ordinary PostgreSQL bigint versions well below Lua's 2^53 numeric precision limit).

```http
POST /cache/lookup
Content-Type: application/json

{"cacheKey":"product:1","endpoint":"GET:/products/:id"}
```

Hit (200):

```json
{"hit":true,"tier":"local","value":{"id":1,"name":"Product 1","payload":"x","version":1,"updatedAt":"2026-10-08T00:00:00Z"},"sourceVersion":1,"fetchedAt":"2026-10-08T00:00:00Z","expiresAt":"2026-10-08T00:01:00Z"}
```

Miss (200): `{"hit":false,"tier":"miss"}`. Tiers are `local`, `redis`, `miss`. Cache failure returns 503 and the main service falls back to the database.

```http
POST /cache/insert
Content-Type: application/json

{"cacheKey":"product:1","endpoint":"GET:/products/:id","value":null,"sourceVersion":1,"fetchedAt":"2026-10-08T00:00:00Z","dbFetchSeconds":0.004}
```

Use a current `fetchedAt` when trying this example. Response: `{"cached":true}`. An already expired fill or cache failure returns 503; main still returns the valid database result. `value` must be present but can be `null`. `dbFetchSeconds` is a duration, not a TTL.

`POST /cache/invalidate` accepts the lookup body and returns `{"invalidated":true}`. It clears this sidecar's local copy and the Redis entry. It is not broadcast invalidation.

`GET /healthz` returns `{"status":"ok"}`. `GET /readyz` returns `{"status":"ready"}` or 503 `{"status":"not_ready"}`. `GET /metrics` serves Prometheus text. `GET /products/1` returns the product and `X-Cache-Tier: database|local|redis`; invalid IDs return 400, missing rows 404, database failure 503.

The complete typed `/analyze` contract is in `internal/system/types.go`: `schemaVersion`, `jobId`, monotonic `sequence`, `endpoint`, `history`, `current` (window start/end, accesses/hits/misses/rate and per-key aggregates), `currentPolicies`, `observations`, `resources`, and `bounds`. Response:

```json
{"schemaVersion":1,"jobId":"GET:/products/:id:1","decisions":[{"cacheKey":"product:1","ttlSeconds":60}]}
```

Policy application is internal; there is no public policy-setting route.

`examples/analyze.json` is a complete illustrative workflow request (its measurements are example data). Try `curl -H "Content-Type: application/json" --data-binary @examples/analyze.json http://localhost:8082/analyze`. With insufficient history it returns the default 60-second TTL. Calling the workflow directly does not apply a sidecar policy.

## Configuration

Copy `.env.example` to `.env` to override the Compose variables shown there. Additional service settings can be set directly in Compose `environment` or the shell for local binaries. Go durations use `ms`, `s`, `m` suffixes.

| Variable | Default |
|---|---|
| `MODE` | `adaptive` (`none`, `fixed`, `adaptive`) |
| `DEFAULT_TTL_SECONDS` / `MIN_TTL_SECONDS` / `MAX_TTL_SECONDS` | 60 / 1 / 3600 |
| `MAX_FRESHNESS_SECONDS` | 3600 (must be >= max TTL) |
| `LOCAL_CAPACITY` / `POLICY_CAPACITY` | 1000 / 10000 |
| `POLICY_LIFETIME` | 10m |
| `BATCH_SIZE` / `FLUSH_INTERVAL` | 100 / 5s |
| `QUEUE_CAPACITY` / `WORKERS` / `HISTORY_SIZE` | 64 / 2 / 8 |
| `CACHE_TIMEOUT` / `DB_TIMEOUT` / `AI_TIMEOUT` | 100ms / 2s / 2s |
| `AI_RETRIES` / `AI_LATENCY` / `AI_FAILURE` | 2 / 0s / empty |
| `SHUTDOWN_TIMEOUT` / `BODY_LIMIT` | 10s / 1048576 bytes |
| `ENDPOINTS` | `GET:/products/:id` (comma-separated allowlist) |
| `ADDR` | app :8080, sidecar :8081, workflow :8082 |
| `REDIS_ADDR` | localhost:6379 (Compose: redis:6379) |
| `SIDECAR_URL` / `AI_URL` | http://localhost:8081 / http://localhost:8082 |
| `DATABASE_URL` | postgres://cache:cache@localhost:5432/cache?sslmode=disable |

Redis has a 128 MB limit and `allkeys-lru` eviction, configured explicitly in `compose.yaml`. Redis persistence is disabled for the disposable cache. PostgreSQL persists in its named volume. Use identical limits and timeout settings in comparisons.

## Verification and smoke

```sh
gofmt -w cmd internal
go vet ./...
go test ./...
go test -race ./...
```

The race detector needs a C compiler. Windows without one can run all checks, including real Redis/PostgreSQL integration, in the supplied Go container:

```sh
docker compose run --rm verify
```

Without `TEST_REDIS_ADDR` and `TEST_DATABASE_URL`, the two real-dependency tests explicitly skip. The container supplies both. Tests cover tiers/nulls, default/learned/expired policies, original-fetch expiry, CAS races, concurrent fills, access/fill counts, batch size/timer/history, queue drops, decision ordering, malformed workflow responses, sidecar failures, singleflight and shutdown.

For the executable smoke, use `make smoke` or, in PowerShell:

```powershell
./scripts/smoke.ps1
```

This uses `compose.smoke.yaml` (2-second default, 3-second maximum TTL, batches of four), checks miss → hit → batch → workflow → applied TTL → later expiry, stops AI and asserts successful requests, then restarts AI. Restore normal settings with `docker compose up -d`. The integration test also checks that AI failures actually occurred while requests succeeded.

## Evaluation

```sh
docker compose run --rm --entrypoint /load tools -url http://app:8080 -sidecar http://sidecar:8081 -scenario hot -duration 10s -rate 100 -keys 1000 -payload 1024 -seed 42 -validate -out /results/smoke.json -samples /results/smoke-samples.jsonl
docker compose run --rm --entrypoint /validate tools -samples /results/smoke-samples.jsonl
```

`-payload` records the expected seeded size; use the same size with the seed utility. The generator never reseeds the DB inside measured traffic. Its bounded workers and bounded pending queue use an open-loop schedule; saturation drops offered work and reports `generatorDropped`. Latency covers HTTP round trip and body read; JSON decoding and validation queries are outside timing. Requested base RPS, offered/sent/completed counts, achieved RPS including drain, percentiles, errors, hit rate, raw before/after Prometheus metrics, and optional freshness results are exported. Metrics contain database read counters, queue drops/depth/age, heap/process resource samples and AI timings. Use Prometheus for the full resource/queue time series rather than interpreting endpoint snapshots as peaks.

Scenarios: `hot` (90% to the hottest 1%), `changing` (hot set moves each quarter), `burst` (3× rate in the middle third), `uniform`, `unique` (sequential never-repeated IDs), `updates` (hot traffic plus independently scheduled seeded DB updates). For `unique`, seed at least the number of offered requests to avoid measuring nonexistent rows. For updates use `-update-rate 10`; invalidation is **disabled in all modes**, so stale data remains until expiry. A separate updater is also available:

```sh
docker compose run --rm tools -mode update -keys 1000 -rate 10 -duration 60s -seed 42
```

Compare `MODE=none`, `MODE=fixed`, `MODE=adaptive` by setting it in `.env`, then running `docker compose up -d`. Before each trial, stop app/sidecar, clear **this prototype's Redis database only** with `docker compose exec redis redis-cli FLUSHDB`, reseed the same key count/payload, and restart app/sidecar to clear local entries, histories, policies and process counters. Run identical scenario/rate/duration/seed/workers, using distinct output paths. Repeat trials and report variation; scheduling and update timing are not bit-for-bit deterministic even with seeded selections. Singleflight remains enabled in all modes.

PowerShell can automate these cold-cache comparisons after startup: `./scripts/benchmark.ps1 -Scenarios hot,changing,burst,uniform,unique,updates -Duration 10s -Rate 100 -Keys 1000`. Stop any second app/sidecar pair before comparisons. The script restores the previous mode at completion; output filenames are overwritten on a repeated run, so copy each trial's results before rerunning.

The validator queries the authoritative version separately, counting `validationDatabaseReads` apart from `database_read` application counters. Matching versions are fresh; a newer version whose `updated_at` precedes request start proves staleness; a later update is indeterminate. `staleRate` uses only classifiable responses and is `null` if none are classifiable. Report indeterminate/error counts alongside it. Post-run validation cannot reconstruct every historical DB version; it deliberately avoids claiming exact staleness in those cases.

For more load increase rate, duration, seeded keys and workers together, and inspect generator drops and achieved rate. To run two independent app/sidecar pairs sharing Redis:

```sh
docker compose --profile multi up -d
# second application: http://localhost:8090, second sidecar: http://localhost:8091
```

Run a generator per app, with corresponding `-url` and `-sidecar`. Policies and local caches remain per sidecar; local copies do not receive other sidecars' policy updates/invalidation. Redis CAS protects values but does not provide global policy ordering or cache coherence. Every sidecar still enforces its configured freshness ceiling. Configure disjoint canonical key namespaces for different endpoints and consistent freshness bounds across replicas.

## Metrics and limits

`app_request_seconds`, `database_read_seconds`, `cache_lookup_seconds`, and `ai_processing_seconds` are histograms. `cache_events_total{kind=...}` tracks access/fill outcomes, DB reads, sidecar errors, batches/drops, AI failures, rejected/out-of-order policies, applied policies and local eviction/expiration. `cache_state{kind=...}` exposes queue depth/oldest age, local/policy entry counts and policy age/timestamp. Standard Go and process collectors are included; OS-specific process metrics may be unavailable on Windows. Keys are never Prometheus labels; tier/outcome/event-kind labels are bounded constants.

This is a single-host container prototype, not evidence of distributed production capacity. No real model training, distributed invalidation, durable policy storage, authentication or production deployment hardening is included. Versions reflect writes made through the seed/update utilities; external writers must also increment `version` and set `updated_at`. Clock synchronization is assumed between app, sidecar, validator and Redis. Queue drops, unavailable observations, partial policy application and validation uncertainty must be reported in research results.
