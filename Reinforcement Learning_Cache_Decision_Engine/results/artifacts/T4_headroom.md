# T4 - headroom

| capacity | best baseline (by val U) | agent | OHR best | OHR agent | OHR Belady (TTL-constrained, unit-size) | OHR Belady plain | OHR headroom captured | stale% best | stale% agent | stale reduction vs best (bound = 100%) |
|---|---|---|---|---|---|---|---|---|---|---|
| 0.0100 | evict:s3fifo/redis/3600s | dqn:main | 0.4410 | 0.3625 | 0.5634 | 0.5651 | -0.6409 | 3.4344 | 0.7561 | 0.7798 |
| 0.0100 | evict:s3fifo/redis/3600s | dqn:bandit | 0.4410 | 0.3531 | 0.5634 | 0.5651 | -0.7182 | 3.4344 | 0.7168 | 0.7913 |
| 0.0100 | evict:s3fifo/redis/3600s | tabq:qbin | 0.4410 | 0.3654 | 0.5634 | 0.5651 | -0.6174 | 3.4344 | 0.9362 | 0.7274 |
| 0.0500 | evict:s3fifo/redis/3600s | dqn:main | 0.6394 | 0.5816 | 0.7796 | 0.7889 | -0.4117 | 5.9383 | 4.6938 | 0.2096 |
| 0.0500 | evict:s3fifo/redis/3600s | dqn:bandit | 0.6394 | 0.6088 | 0.7796 | 0.7889 | -0.2176 | 5.9383 | 4.1621 | 0.2991 |
| 0.0500 | evict:s3fifo/redis/3600s | tabq:qbin | 0.6394 | 0.6034 | 0.7796 | 0.7889 | -0.2564 | 5.9383 | 4.0047 | 0.3256 |
| 0.2500 | evict:lru/redis/3600s | dqn:main | 0.8281 | 0.7961 | 0.8947 | 0.9262 | -0.4799 | 7.8547 | 12.5790 | -0.6015 |
| 0.2500 | evict:lru/redis/3600s | dqn:bandit | 0.8281 | 0.8205 | 0.8947 | 0.9262 | -0.1138 | 7.8547 | 11.5466 | -0.4700 |
| 0.2500 | evict:lru/redis/3600s | tabq:qbin | 0.8281 | 0.5931 | 0.8947 | 0.9262 | -3.5241 | 7.8547 | 6.5587 | 0.1650 |

Belady bounds use unit-size objects and object-count capacity, so they are loose upper bounds on OHR for byte-capacity caches; negative values mean the agent is WORSE than the best baseline.
