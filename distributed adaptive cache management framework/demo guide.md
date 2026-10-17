# Demo guide — understand it first, then demonstrate it

This guide is written for Windows PowerShell, from this project's root folder. Work through sections 1–6 first; you do not need to understand every Go file before presenting the demo.

## 1. What have we built?

We built a **backend caching research prototype**. It serves sample products through an HTTP API. It is not a shopping website. Seeing JSON at `http://localhost:18080/products/1` is expected.

The research question is: **Can we change how long each product stays cached using decisions computed in the background, without making product requests wait for those decisions?**

TTL means **time to live**. A 60-second TTL permits an entry to be reused until its original fetch time plus 60 seconds. After expiry, a new request must find another valid cache copy or read the database.

### The parts, in plain language

| Part | Its job | Where to look |
|---|---|---|
| Main Go application | Receives `GET /products/1`; asks the sidecar; reads PostgreSQL on a miss | `cmd/app`, `internal/system/app.go` |
| Sidecar | Separate Go service that handles cache lookup, insertion, statistics and policies | `cmd/sidecar`, `internal/system/sidecar.go` |
| Local cache | Bounded map/LRU inside the sidecar's memory; checked first | `internal/system/cache.go` |
| Redis | Shared second cache; checked when the local cache misses | `internal/system/redis.go` |
| PostgreSQL | Authoritative product records, including a version and update time | `migrations/001_products.sql` |
| Metrics buffer and queue | Collect access statistics and hand batches to background workers | `internal/system/pipeline.go` |
| Mock AI workflow | One service containing mock predictor and mock policy-agent components | `cmd/workflow`, `internal/system/workflow.go` |
| Prometheus | Polls the services' `/metrics` endpoints and stores measurements | `prometheus.yml` |
| Grafana | Draws dashboards using those measurements | `observability/grafana/` |
| Load generator | Simulates many clients so the behavior and charts become visible | `cmd/load` |

**Mock LSTM and mock RL are not trained models.** They are replaceable deterministic rules that exercise the communication, queue and TTL-update pipeline. They are two components inside the one workflow service, not two additional containers. No training dataset or training process is included.

### Follow one product request

```text
You ask for /products/1
          |
     Main application
          |
        Sidecar
          |
     Local cache -- hit --> return product
          |
         miss
          |
        Redis ----- hit --> copy to local without restarting expiry; return
          |
         miss
          |
 Main reads PostgreSQL
          |
 Main asks sidecar to cache the result
          |
 Return the product
```

The main application waits briefly for cache lookup and insertion. Cache failures fall back to PostgreSQL; a failed insertion does not discard a successful DB result. It never calls the AI service.

### Follow the separate background work

```text
Lookups produce access statistics
          |
100 accesses OR 5-second timer (normal defaults)
          |
Create a batch and put it in a bounded queue
          |
Worker calls workflow /analyze
          |
Mock predictor estimates demand from recent windows
          |
Mock policy agent selects a TTL per key
          |
Sidecar validates the decisions and updates its policies
```

AI controls **TTL only**. The lookup order always stays **local → Redis → database**. It does not choose placement. A TTL change is calculated from the entry's original `fetchedAt`, so it does not give old data a fresh lifetime starting now.

### Your opening explanation

> “This is an asynchronous adaptive caching prototype. Product requests use a local cache and Redis before PostgreSQL. Separately, access statistics are batched and processed by a mock prediction-and-policy workflow. Its decisions update per-key TTLs. The real models are future replacements; today I am demonstrating the working system around them.”

## 2. Start the system and open the right screens

Open **two PowerShell terminals**. Use Terminal A for control and inspection; use Terminal B for load generation.

In both terminals:

```powershell
Set-Location 'E:\SLIIT\Y4 S1\IT4010 - Research\AI Adaptive Caching'
```

In Terminal A:

```powershell
docker compose up -d --build
docker compose ps
```

The first build/pull can take several minutes. Start Docker Desktop first. Normal running services are `app`, `sidecar`, `workflow`, `postgres`, `redis`, `prometheus`, and `grafana`. `tools`, `verify`, `app2` and `sidecar2` are optional; they do not need to be running.

| Screen | URL | What it is |
|---|---|---|
| Product API | http://localhost:18080/products/1 | Product JSON, not a dashboard |
| App readiness | http://localhost:18080/readyz | Should say `ready` |
| Prometheus targets | http://localhost:9090/targets | Three application targets should be UP |
| Prometheus query screen | http://localhost:9090 | Run individual metric queries |
| Grafana: request path | http://localhost:13000/d/cache-request-path | First dashboard to show |
| Grafana: background AI | http://localhost:13000/d/cache-background | Second dashboard to show |

This workspace's `.env` sets `APP_PORT=18080`. Container-to-container traffic still uses `app:8080`. If you change the host port, update the host commands below. `GRAFANA_PORT` defaults to 13000.

Grafana is now included and auto-provisions its Prometheus data source and both dashboards. You do not need to import anything or configure a URL in Grafana. Anonymous **Viewer** access is enabled on the localhost-only port for this demo. Editing is managed by the JSON files; optional admin login is `admin` / `local-demo-admin` unless you override it. These are local demo settings.

### Check readiness before continuing

Define this helper in Terminal A:

```powershell
function Wait-DemoReady {
    param([string]$Url)
    for ($i = 0; $i -lt 30; $i++) {
        try {
            if ((Invoke-RestMethod -Uri $Url -TimeoutSec 2).status -eq 'ready') { return }
        } catch { }
        Start-Sleep -Seconds 1
    }
    throw "Service did not become ready: $Url"
}
Wait-DemoReady 'http://localhost:18080/readyz'
Wait-DemoReady 'http://localhost:8081/readyz'
```

Initial database creation seeds 1,000 products. If products are missing, run `docker compose run --rm tools -mode seed -keys 1000 -payload 1024`. Seeding existing records changes their versions; do it before your presentation, not during a measurement.

## 3. Prove a miss becomes a hit — about 2 minutes

Do this before sustained load. Stop any old load-generator run. In Terminal A, define:

```powershell
$lookupBody = @{ cacheKey = 'product:1'; endpoint = 'GET:/products/:id' } | ConvertTo-Json

function Show-Product {
    $response = Invoke-WebRequest 'http://localhost:18080/products/1'
    $product = $response.Content | ConvertFrom-Json
    [pscustomobject]@{
        Status = [int]$response.StatusCode
        Tier = ($response.Headers['X-Cache-Tier'] -join ',')
        ProductId = $product.id
        Version = $product.version
    }
}

# Clear only product:1 from this sidecar and Redis, not the database.
Invoke-RestMethod -Method Post -Uri 'http://localhost:8081/cache/invalidate' -ContentType 'application/json' -Body $lookupBody

Show-Product
Show-Product
```

Expected:

```text
Status  Tier      ProductId  Version
200     database  1          <current version>
200     local     1          <same version>
```

Say: **“The first request had no cached copy, so it read PostgreSQL. The next request was served from the sidecar's local memory.”** The product body can be identical on both requests; the `X-Cache-Tier` response header tells you where it came from. Do not rely on visually refreshing JSON or assume a particular version number.

If the second request says `database`, check that `MODE` is `adaptive` or `fixed`, that the sidecar is ready, and that the entry has not expired. `redis` is also a cache hit, but from the second tier.

### Optional: prove Redis is the second tier

After the two successful requests above, while the entry is still valid:

```powershell
docker compose restart sidecar
Wait-DemoReady 'http://localhost:8081/readyz'
Show-Product
Show-Product
```

Expected: first `redis`, then `local`. Restarting clears local memory and policies but preserves Redis. Complete this within the normal 60-second default lifetime; if it expires, repeat the invalidate/fill sequence. Other running load can affect the TTL, so do this before the next section.

Say: **“The sidecar lost its memory on restart, but Redis still had the value. Promoting it back to local memory preserves its expiry.”**

## 4. Put traffic on the dashboards — about 3 minutes

In Terminal B:

```powershell
docker compose run --rm --entrypoint /load tools -url http://app:8080 -sidecar http://sidecar:8081 -scenario hot -duration 90s -rate 100 -keys 1000 -seed 42 -out /results/demo-hot.json -samples /results/demo-hot-samples.jsonl
```

This requests 100 requests/second for 90 seconds. The seeded scenario sends about 90% of requests to the hottest 1% of keys. Achieved load can differ; the exported result reports it. Keep this terminal running while using Terminal A and the browser. Increase duration to `180s` if you want longer to explain.

In Grafana choose **Last 15 minutes**, with **5s refresh**. Allow 10–15 seconds for scraping and at least one minute for the rolling-rate charts to settle. Sparse manual requests alone will not create smooth charts.

### Dashboard 1: Request path

| Panel | What you should explain |
|---|---|
| Service availability | App, sidecar and workflow scrape targets normally show 1. This is scrape health, not a guarantee that every dependency is ready. |
| Application requests/second | Confirms the generator is actually producing traffic. |
| Application latency — p95 | Estimated time within which 95% of requests finish, based on histogram buckets. It is not average latency. |
| Database reads/second | Should be below total request rate once repeated products are cached. Singleflight also coalesces overlapping misses. |
| Cache lookups by tier | Most repeated accesses should show as local hits; new/expired entries show as misses. Redis hits may be rare with one warm sidecar. |
| Cache hit rate | Fraction of sidecar lookups that hit local or Redis. There is no meaningful ratio when no lookups occur. |
| Errors and local entries | Check request/insert failures and the number of current local entries. |
| Go heap usage | Application-process heap memory, not Redis or PostgreSQL memory. |

Say: **“We can see requests continuing, many lookups being served by local memory, and fewer reads going to PostgreSQL.”** Do not promise lower latency: an extra sidecar HTTP call can cost more than a very fast local database query. The earlier smoke trial showed that possibility.

### Dashboard 2: Background AI

Open http://localhost:13000/d/cache-background while traffic continues.

| Panel | What it means |
|---|---|
| Analysis batches/second | Lookups are being aggregated into jobs. |
| Workflow calls/second | The sidecar is contacting the mock workflow. Retries can create extra calls. |
| Applied key policies/second and process total | Validated decisions were applied. A batch may update many keys; repeated application of the same TTL also increments this counter. |
| AI job duration — p95 | Includes the workflow call, retries/backoff and policy application. It is not pure model inference time. |
| Failed AI jobs | Failures are recorded in the background. |
| Queue depth/age and dropped batches | Whether workers are keeping up. A queue that stays at zero is normal under light load. |
| Oldest active policy age | Time since policy application, not remaining TTL or database freshness. |

Say: **“Requests generate batches; workers invoke the workflow; its decisions are validated and applied separately from serving products.”**

### Inspect the actual TTL for a key

While or immediately after traffic is running, in Terminal A:

```powershell
$entry = Invoke-RestMethod -Method Post -Uri 'http://localhost:8081/cache/lookup' -ContentType 'application/json' -Body $lookupBody
if ($entry.hit) {
    [pscustomobject]@{
        Tier = $entry.tier
        SourceVersion = $entry.sourceVersion
        FetchedAt = $entry.fetchedAt
        ExpiresAt = $entry.expiresAt
        TotalTTLSeconds = [math]::Round((([datetimeoffset]$entry.expiresAt) - ([datetimeoffset]$entry.fetchedAt)).TotalSeconds, 2)
        RemainingSeconds = [math]::Round((([datetimeoffset]$entry.expiresAt) - [datetimeoffset]::UtcNow).TotalSeconds, 2)
    }
} else {
    'Entry is absent/expired. Run Show-Product to fill it, then repeat this block.'
}
```

`TotalTTLSeconds` is lifetime measured from the original fetch. `RemainingSeconds` decreases as time passes. A policy can change the total lifetime. These are different quantities. This diagnostic lookup itself adds an access event.

The default is 60 seconds. With less than two historical windows, the mock uses that default. Later it uses demand and observed update information; it may choose a **shorter or longer** TTL. Do not promise a particular number. For implementation details, the demand rule is in `MockLSTM.Predict`, and the TTL rule is in `MockRL.Decide` in `internal/system/workflow.go`.

Individual key TTLs are intentionally **not** Prometheus labels or time series. Use this lookup to inspect a key. Grafana's policy counter alone is not proof that a TTL value changed. For background logs: `docker compose logs --tail 20 sidecar` and look for `policy applied`.

## 5. Prove AI failure does not stop the application — about 2 minutes

Ensure Terminal B is still generating traffic; start another 90-second load run if necessary. Keep both dashboards open. In Terminal A:

```powershell
try {
    docker compose stop workflow
    1..5 | ForEach-Object { Show-Product }
    Start-Sleep -Seconds 15
    docker compose logs --tail 10 sidecar
} finally {
    docker compose start workflow
}
```

Expected:

- Product requests continue returning HTTP 200 while PostgreSQL/cache are healthy.
- After the next scrape, workflow availability shows 0 while it is stopped.
- As batches are processed, failed AI jobs increase and sidecar logs show analysis failures.
- Existing/default TTL policies keep working. After workflow restarts, calls and policy applications resume when new batches are produced.

Say: **“AI is unavailable, but it is not on the product request path. Requests can continue using cache or PostgreSQL; only new adaptive decisions are affected.”**

If you interrupt the demo manually, run `docker compose start workflow` yourself. Counters need requests/batches to change; stopping AI while the application is idle does not create failed jobs by itself. The one-minute rate chart can continue showing recent failures after recovery.

## 6. How to demonstrate expiry reliably

For a quick automated proof, stop sustained load and run:

```powershell
./scripts/smoke.ps1
```

This temporarily uses `compose.smoke.yaml`: 2-second default TTL, 3-second maximum freshness, batches of four and a 250 ms flush timer. It prints PASS checks for miss → hit → batch → workflow → policy application → expiry, then checks the AI-outage case and restarts the workflow.

**Restore normal settings afterward:**

```powershell
docker compose up -d app sidecar workflow
```

Do not mix smoke measurements with the normal dashboard demonstration: these settings deliberately accelerate expiry and recreate services, which resets their counters. All three modes should use the same settings in a fair comparison.

## 7. Prometheus walkthrough: where the charts come from

Prometheus stores and queries measurements; Grafana visualizes them. Neither chooses cache TTLs. Go services export `/metrics`, Prometheus scrapes every 5 seconds, and Grafana queries Prometheus. Browser refresh alone does not trigger an AI decision.

First open http://localhost:9090/targets. The expected application targets are `app:8080`, `sidecar:8081`, and `workflow:8082`. These are **Docker network addresses**, so do not replace them with `localhost:18080` in `prometheus.yml`.

At http://localhost:9090, enter a query and select table or graph view:

| Question | PromQL |
|---|---|
| Are services reachable? | `up{job="prototype"}` |
| How many application DB reads since restart? | `cache_events_total{instance="app:8080",kind="database_read"}` |
| Which tiers served lookups? | `cache_lookup_seconds_count{instance="sidecar:8081"}` |
| How many key policies have been applied? | `cache_events_total{instance="sidecar:8081",kind="policy_update"}` |
| How many jobs are waiting now? | `cache_state{instance="sidecar:8081",kind="queue_depth"}` |
| Has AI work failed? | `cache_events_total{instance="sidecar:8081",kind="ai_failure"}` |

For application request rate, use:

```promql
sum(rate(app_request_seconds_count{job="prototype",instance="app:8080"}[1m]))
```

For approximate p95 application latency in milliseconds:

```promql
1000 * histogram_quantile(0.95,
  sum by (le) (rate(app_request_seconds_bucket{job="prototype",instance="app:8080"}[1m]))
)
```

`rate(...[1m])` is an average over the previous minute. `_total`/`_count` counters accumulate until process restart; they are not current rates. Some counters are only created after their first event, so an absent AI-failure series before any failure is expected. Quantiles/hit ratios without traffic are undefined. The dashboards retain No data where a measurement is unknown rather than inventing a latency or TTL.

## 8. Optional: compare no cache, fixed TTL and adaptive TTL

This is a separate experiment after you understand the basic demo. Stop any running load generator and use normal configuration. The comparison script clears this prototype's disposable Redis cache, recreates app/sidecar to clear in-memory state, and reseeds products between trials.

```powershell
./scripts/benchmark.ps1 -Duration 10s -Rate 100 -Keys 1000

Get-ChildItem results -Filter '*-hot.json' | ForEach-Object {
    $r = Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json
    [pscustomobject]@{
        Mode = $_.BaseName
        Requests = $r.sentRequests
        Errors = $r.errors
        AchievedRPS = [math]::Round($r.achievedRPS, 2)
        P95ms = $r.p95Ms
        DBReads = $r.databaseReads
        HitPercent = [math]::Round(100 * $r.hitRate, 1)
    }
} | Format-Table -AutoSize
```

| Mode | What changes |
|---|---|
| `none` | Main bypasses the sidecar and queries PostgreSQL; per-instance singleflight still operates. |
| `fixed` | Local/Redis caching with default TTL; no background adaptive analysis. |
| `adaptive` | Same cache tiers, plus background per-key TTL decisions. |

Use the JSON files to compare trials. The Grafana charts do not label traffic by mode and old samples remain in the selected time range after restarts. Do not interpret one continuous chart as three automatically labeled experiment results.

An ordinary workload produces no known DB changes, so stale-response analysis needs the separate update scenario and validator. A cache hit does not prove freshness. The validator runs DB reads outside request timing and reports indeterminate cases when later updates prevent a reliable historical comparison. See `VERIFICATION.md` for actual earlier measurements, including one reported updater error. No live staleness metric is exported to Grafana.

## 9. A short presentation script

1. **Problem:** “Fixed TTLs require a developer to pick a lifetime that may not suit every key.”
2. **Request demo:** Show a database miss, then a local hit using `Show-Product`.
3. **Architecture:** Explain main app, sidecar, local cache, Redis and PostgreSQL.
4. **Live traffic:** Show requests, cache hits and database reads on dashboard 1.
5. **Background adaptation:** Show batches, workflow calls and policy updates on dashboard 2; inspect one actual entry's timestamps.
6. **Failure isolation:** Stop AI while traffic continues; show successful requests and recorded AI failures; restart AI.
7. **Scope:** “The pipeline is implemented and tested. Prediction and policy selection are mock components; trained LSTM/RL integration and rigorous evaluation remain future work.”

A full presentation can take 10–15 minutes. Do the initial image downloads/build before presenting. Keep the presentation focused on behavior, then use the code map below if someone asks how it works internally.

## 10. Code reading order

Read these in order, rather than starting with the entire repository:

1. `internal/system/app.go` → `product`: one user request.
2. `internal/system/cache.go` → `Lookup`, `Fill`, `Apply`: tiers and expiry.
3. `internal/system/pipeline.go` → `Record`, `flushLocked`, `process`, `apply`: how work moves into the background.
4. `internal/system/workflow.go` → predictor then policy agent: what the mocks do.
5. `internal/system/types.go`: the JSON contracts connecting the services.
6. `internal/system/system_test.go`: correctness and failure scenarios.

The original `Pseudocode/` still contains the starting design. The executable implementation is in `cmd/` and `internal/`.

## 11. Troubleshooting and stopping

| Symptom | What to check |
|---|---|
| Product browser shows JSON | Correct: this is the API. Open port 13000 for dashboards. |
| API unavailable | `docker compose ps`, `docker compose logs --tail 20 app`, app `/readyz`. |
| Grafana unavailable | `docker compose logs --tail 30 grafana`; check port 13000 or `GRAFANA_PORT`. |
| Grafana opens but no dashboard | Open `/d/cache-request-path` directly; provisioning files live under `observability/grafana/`. |
| Dashboard has No data | Check Prometheus targets, run traffic, select Last 15 minutes, wait for scrapes. Unused counters/idle ratios can legitimately have no data. |
| Queue is always zero | Workers are keeping up. That is a valid result, not proof of a broken queue. |
| Policy updates stay zero | Confirm `MODE=adaptive`, workflow is running, and lookups are being generated. |
| TTL always initially 60 | The default is used until sufficient history exists; let traffic run. Policy applications can also choose the same value. |
| Tier stays database | Check MODE, sidecar readiness, expired entries, and insertion errors. |
| Unexpected old graph values | Choose a narrower time range; Prometheus retains past samples across app restarts. |
| `Show-Product` not recognized | Define the helper in the current PowerShell terminal using section 3. |
| Product version changed | Seeding/updating increments versions. Use the current value, not a hardcoded demo value. |

Stop the stack with `docker compose down`. This preserves named database/Grafana volumes. Do not use `down -v` as part of an ordinary demo; that deletes the named data volumes. The existing Prometheus setup does not have a named persistent data volume, so do not rely on its history surviving container replacement; save benchmark JSON and screenshots for evidence.

Grafana provisioning follows the official [provisioning documentation](https://grafana.com/docs/grafana/latest/administration/provisioning/) and [Docker setup](https://grafana.com/docs/grafana/latest/setup-grafana/installation/docker/). Full implementation details are in `README.md`; executed engineering checks and prior benchmark evidence are in `VERIFICATION.md`.

## Guide verification

The miss/hit commands were exercised against the running stack and returned `200/database`, then `200/local`. All three Prometheus targets were UP. Both dashboards were confirmed as provisioned and readable without login, and all 22 panel expressions were accepted by Prometheus. A 30-second check at 50 requested requests/second completed 1,500 requests with zero errors, 89% cache hit rate and 307 applied key policies. This checks the demo wiring; it is not evidence of trained-AI performance. Query results are saved in `evidence/dashboard-query-checks.json`, and load results in `evidence/dashboard-demo-load.json`.
