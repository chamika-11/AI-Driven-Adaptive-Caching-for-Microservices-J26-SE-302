# T5 - overhead (measured on this PC)

| item | value |
|---|---|
| numpy forward pass of the 19-128-128-45 dueling network (us) | 19.8000 |
| full per-decision overhead incl. feature tracking, simulator-measured (us) | 203.7000 |
| decisions per 1,000 reads (test slice, 1% capacity, rule policy) | 653.8000 |
| amortised overhead per read (us) | 133.2000 |
| mean read latency in the model (us), rule policy | 5243.2000 |
| overhead as % of mean read latency (control-plane cost, NOT in the model) | 2.5400 |
| network parameters (bytes, float32) | 100024 |
| feature-tracker state (bytes, 8 B per list element: per-key tables + request/hit rings + rate bins) | 244816 |
| feature-tracker state per key (bytes) | 61.2000 |
| training: 300,000 decisions, one core (s), from run notes | about 500-600 |

Pure-Python simulator timings; absolute values depend on the machine. The decision overhead is control-plane cost: it is not added to the modelled request latency. Metadata is NOT charged against cache capacity (R-E8 / T6 not run).
