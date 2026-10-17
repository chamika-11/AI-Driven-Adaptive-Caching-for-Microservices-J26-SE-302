# T1 - baseline inventory

| policy | family | tier/role | implementation | parameters | tuning budget | per-key metadata bytes (estimate) |
|---|---|---|---|---|---|---|
| fixed:local/5s/low | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:local/5s/normal | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:local/5s/high | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:local/30s/low | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:local/30s/normal | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:local/30s/high | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:local/120s/low | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:local/120s/normal | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:local/120s/high | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:local/600s/low | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:local/600s/normal | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:local/600s/high | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:local/3600s/low | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:local/3600s/normal | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:local/3600s/high | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:redis/5s/low | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:redis/5s/normal | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:redis/5s/high | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:redis/30s/low | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:redis/30s/normal | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:redis/30s/high | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:redis/120s/low | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:redis/120s/normal | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:redis/120s/high | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:redis/600s/low | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:redis/600s/normal | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:redis/600s/high | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:redis/3600s/low | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:redis/3600s/normal | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:redis/3600s/high | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:both/5s/low | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:both/5s/normal | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:both/5s/high | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:both/30s/low | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:both/30s/normal | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:both/30s/high | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:both/120s/low | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:both/120s/normal | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:both/120s/high | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:both/600s/low | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:both/600s/normal | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:both/600s/high | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:both/3600s/low | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:both/3600s/normal | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| fixed:both/3600s/high | fixed | TTL ladder x placement | this project (Python) | 45 actions, fixed | none (fixed before evaluation) | 0 |
| random:45 | random | floor | this project | uniform over 45 actions | none (fixed before evaluation) | 0 |
| stat_ttl:mean/redis | stat_ttl | statistics TTL | this project | key gap statistic (fit slice), snapped to bucket | none (fixed before evaluation) | 8 |
| stat_ttl:mean/both | stat_ttl | statistics TTL | this project | key gap statistic (fit slice), snapped to bucket | none (fixed before evaluation) | 8 |
| stat_ttl:median/redis | stat_ttl | statistics TTL | this project | key gap statistic (fit slice), snapped to bucket | none (fixed before evaluation) | 8 |
| stat_ttl:median/both | stat_ttl | statistics TTL | this project | key gap statistic (fit slice), snapped to bucket | none (fixed before evaluation) | 8 |
| stat_ttl:p10/redis | stat_ttl | statistics TTL | this project | key gap statistic (fit slice), snapped to bucket | none (fixed before evaluation) | 8 |
| stat_ttl:p10/both | stat_ttl | statistics TTL | this project | key gap statistic (fit slice), snapped to bucket | none (fixed before evaluation) | 8 |
| pred_ttl:redis | pred_ttl | predictor TTL | this project | stand-in predictor tables | none (fixed before evaluation) | 8 |
| pred_ttl:both | pred_ttl | predictor TTL | this project | stand-in predictor tables | none (fixed before evaluation) | 8 |
| aimd:a60/b0.5 | aimd | adaptive TTL | this project | alpha {60,300}s, beta {0.5,0.25} | none (fixed before evaluation) | 8 |
| aimd:a60/b0.25 | aimd | adaptive TTL | this project | alpha {60,300}s, beta {0.5,0.25} | none (fixed before evaluation) | 8 |
| aimd:a300/b0.5 | aimd | adaptive TTL | this project | alpha {60,300}s, beta {0.5,0.25} | none (fixed before evaluation) | 8 |
| aimd:a300/b0.25 | aimd | adaptive TTL | this project | alpha {60,300}s, beta {0.5,0.25} | none (fixed before evaluation) | 8 |
| place_hash:0.10 | place_hash | placement rule (post-hoc) | this project | fraction {0.10,0.25,0.50} local | none (fixed before evaluation); added post-hoc (M6-B) | 0 |
| place_hash:0.25 | place_hash | placement rule (post-hoc) | this project | fraction {0.10,0.25,0.50} local | none (fixed before evaluation); added post-hoc (M6-B) | 0 |
| place_hash:0.50 | place_hash | placement rule (post-hoc) | this project | fraction {0.10,0.25,0.50} local | none (fixed before evaluation); added post-hoc (M6-B) | 0 |
| place_size:p25 | place_size | placement rule (post-hoc) | this project | size percentile {25,50,75} | none (fixed before evaluation); added post-hoc (M6-B) | 0 |
| place_size:p50 | place_size | placement rule (post-hoc) | this project | size percentile {25,50,75} | none (fixed before evaluation); added post-hoc (M6-B) | 0 |
| place_size:p75 | place_size | placement rule (post-hoc) | this project | size percentile {25,50,75} | none (fixed before evaluation); added post-hoc (M6-B) | 0 |
| place_freq:k2 | place_freq | placement rule (post-hoc) | this project | k {2,3,5} in last 1,000 requests | none (fixed before evaluation); added post-hoc (M6-B) | 8 |
| place_freq:k3 | place_freq | placement rule (post-hoc) | this project | k {2,3,5} in last 1,000 requests | none (fixed before evaluation); added post-hoc (M6-B) | 8 |
| place_freq:k5 | place_freq | placement rule (post-hoc) | this project | k {2,3,5} in last 1,000 requests | none (fixed before evaluation); added post-hoc (M6-B) | 8 |
| zerostale_oracle_ttl:redis | oracle_ttl | BOUND (future knowledge) | this project | largest bucket <= time to next write | none (fixed before evaluation) | 0 |
| zerostale_oracle_ttl:both | oracle_ttl | BOUND (future knowledge) | this project | largest bucket <= time to next write | none (fixed before evaluation) | 0 |
| belady_ttl_constrained | belady | BOUND (future knowledge) | this project (unit-size objects) | offline | none (fixed before evaluation) | 0 |
| belady_plain | belady | BOUND (future knowledge) | this project (unit-size objects) | offline | none (fixed before evaluation) | 0 |
| evict:lru/redis/3600s | evict | strong eviction (new, E1) | this project, from the SIEVE / S3-FIFO / LRU / FIFO descriptions | TTL 3600 s, placement redis|both | none (fixed before evaluation) | 17 |
| evict:lru/both/3600s | evict | strong eviction (new, E1) | this project, from the SIEVE / S3-FIFO / LRU / FIFO descriptions | TTL 3600 s, placement redis|both | none (fixed before evaluation) | 17 |
| evict:fifo/redis/3600s | evict | strong eviction (new, E1) | this project, from the SIEVE / S3-FIFO / LRU / FIFO descriptions | TTL 3600 s, placement redis|both | none (fixed before evaluation) | 17 |
| evict:fifo/both/3600s | evict | strong eviction (new, E1) | this project, from the SIEVE / S3-FIFO / LRU / FIFO descriptions | TTL 3600 s, placement redis|both | none (fixed before evaluation) | 17 |
| evict:sieve/redis/3600s | evict | strong eviction (new, E1) | this project, from the SIEVE / S3-FIFO / LRU / FIFO descriptions | TTL 3600 s, placement redis|both | none (fixed before evaluation) | 17 |
| evict:sieve/both/3600s | evict | strong eviction (new, E1) | this project, from the SIEVE / S3-FIFO / LRU / FIFO descriptions | TTL 3600 s, placement redis|both | none (fixed before evaluation) | 17 |
| evict:s3fifo/redis/3600s | evict | strong eviction (new, E1) | this project, from the SIEVE / S3-FIFO / LRU / FIFO descriptions | TTL 3600 s, placement redis|both | none (fixed before evaluation) | 17 |
| evict:s3fifo/both/3600s | evict | strong eviction (new, E1) | this project, from the SIEVE / S3-FIFO / LRU / FIFO descriptions | TTL 3600 s, placement redis|both | none (fixed before evaluation) | 17 |

Metadata bytes are estimates (SIEVE: 2 pointers + visited bit; S3-FIFO: freq + queue links; TTL tables: one float per key). ARC, W-TinyLFU, LeCaR, 2Q and libCacheSim baselines are NOT implemented (Addendum M11-E).
