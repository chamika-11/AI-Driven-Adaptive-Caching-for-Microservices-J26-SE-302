"""Profile one or more Twitter trace shards with the project's own streaming parser.

    python scripts/profile_trace.py data/raw/twitter_samples_2020Mar/cluster012 [more files...]

Prints the first 5 raw rows (R-D1 proof: nonzero TTL on `set`), parse statistics and a profile.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from rlcache.trace.parser import iter_raw_rows, parse_trace, profile_trace  # noqa: E402

for path in sys.argv[1:]:
    print(f"== {path}")
    for row in iter_raw_rows(path, limit=5):
        print("  raw:", ",".join(row))
    tr, st = parse_trace(path)
    print("  parse:", {k: v for k, v in vars(st).items()})
    print("  profile:", json.dumps(profile_trace(tr), default=str))
