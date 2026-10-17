# Twitter Twemcache trace — what was attempted, and what exists (2026-10-14/15)

Requirement: R-D1 (obtain a plain-text shard with `op` and `TTL`), R-D6 (cluster12 train /
cluster52 evaluate / cluster22 alternative). Run from the user's own PC (Windows 11), not the
cloud workspace.

## Attempts, in order

| # | Source | Command / action | Result |
|---|---|---|---|
| 1 | CMU PDL FTP, documented path `ftp://ftp.pdl.cmu.edu/pub/datasets/twemcacheWorkload/open_source/` | `curl --list-only` | **curl exit 9.** Server reachable (anonymous login OK, ProFTPD 1.3.5). `CWD twemcacheWorkload` → `550 No such file or directory`. |
| 2 | Same server, parent listing `LIST -a /pub/datasets` | `curl -X "LIST -a"` | `twemcacheWorkload -> /n/twemcacheWorkload` and `cacheDatasets -> /n/cacheDatasets` are **symlinks pointing outside the FTP root** (dated 2020-08-10 / 2024-08-12). They dangle from the anonymous user's view, so the traces are **not reachable via anonymous FTP** at present. `hla`, `ottertune`, `ATLAS` are the only real directories. |
| 3 | HTTPS form of the same path (the repo README's URL) | `curl -I https://ftp.pdl.cmu.edu/...` | HTTP code `000` (no connection / not served over HTTPS). |
| 4 | SNIA IOTTA trace type 17 / key-value 29954 | `curl -L` | HTTP 200, but the page is an anti-bot JavaScript proof-of-work challenge ("Verifying You Are Human"). Download additionally requires cookies and acceptance of the SNIA Trace Data Files licence. **Not attempted further** — accepting a licence and downloading ~1 GB parts is a decision for the owner, not something to do silently. |
| 5 | Baidu Pan mirror (`pan.baidu.com/s/1Jm2nAW-UhsjXU6JYoA07LA`, code `wcws`) | not attempted | Requires a Baidu account / app; not scriptable. |
| 6 | Storj mirror | not attempted | README itself says "not available after Dec 2020". |
| 7 | **Repo `samples/` directory** — `github.com/twitter/cache-trace/samples/2020Mar/clusterNNN` (54 files) | `curl` of `raw.githubusercontent.com/.../cluster012`, `cluster052`, `cluster022` | **Succeeded.** Files are plain text (not zstd), exact byte sizes match the GitHub API listing. |

## What was downloaded

`data/raw/twitter_samples_2020Mar/` (git-ignored; re-download with the URLs above)

| File | Bytes | Rows | Span (trace s) | Unique keys | Ops | Notes |
|---|---:|---:|---:|---:|---|---|
| cluster012 | 66,489,984 | 1,000,000 | **211** | 797,001 | 80% `set`, 20% `get` | `set` TTL = 300 (299/301 jitter); median **1 write per key**, max 11 |
| cluster052 | 44,110,178 | 1,000,000 | **58** | 255,333 | 89% `get`, `gets`, `add`, `cas`, `delete`, 112 `set` | write TTLs 86,400 / 1,209,600 / 43,200 s; median 1 write/key, max 120; keys use `:` namespaces |
| cluster022 | 73,878,699 | 1,000,000 | **553** | 511,774 | `get`, `incr`, `set`, `delete` | write TTLs mostly 86,400 (and 0 on `incr`/`delete`); keys use `|` namespaces; median 2 writes/key, max 418 |

Parse statistics (project parser): 0 malformed rows in all three. **532 / 184 / 259 rows per
million are out of timestamp order** (1-second resolution jitter); the parser stable-sorts and
counts them.

## What this does and does NOT establish

* **R-D1 is satisfied for the schema**: 7 columns, 11-op vocabulary seen across the three files,
  nonzero TTL on `set`/`add`/`cas`/`replace`, TTL 0 on reads (test
  `tests/test_trace_parser.py::test_real_cluster012_prefix_schema`).
* **The samples are 1M-request slices spanning 1–9 minutes.** They cannot exercise TTL buckets of
  120/600/3600 s (nothing expires inside a 211 s trace), and per-key write history is almost
  empty (median 1 write per key), so per-key volatility / predicted-TTL cannot be learned from
  them. They are suitable for: parser validation, operation-mix / size / namespace statistics,
  and a smoke test of the simulator on real request sequences.
* **They are NOT the "cluster12 train / cluster52 evaluate" experiment.** No real-trace
  *experimental* result may be reported until a multi-hour contiguous window of the full shards
  (`clusterN.0.zst`, 1e9 rows) is obtained, or the 87-part SNIA cluster-12 copy.

## Next step for the owner

Either (a) fetch cluster12 / cluster52 from SNIA IOTTA trace type 17 in a browser (JS challenge,
licence acceptance) and place the `.zst` parts under `data/raw/twitter_full/`, or (b) ask the
CMU PDL maintainers (or open an issue on the `twitter/cache-trace` repo) to repair the
`/n/twemcacheWorkload` symlink. The parser already streams `.zst` and slices by time window, so
no code change is needed once the files exist:

```bash
python scripts/profile_trace.py data/raw/twitter_full/cluster12.0.zst
```
