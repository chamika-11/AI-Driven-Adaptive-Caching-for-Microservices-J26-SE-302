"""Append a validated rows file to results/results.csv exactly once (refuses duplicates, never touches old rows).

    python scripts/append_results.py results/evict_baselines.csv
"""
import hashlib
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rlcache.results_schema import append_rows, read_rows  # noqa: E402

src, dst = Path(sys.argv[1]), ROOT / "results" / "results.csv"
new = read_rows(src)
ids = [r["run_id"] for r in new]
assert len(ids) == len(set(ids)), "duplicate run ids inside the new file"
before = dst.read_bytes()
assert not (set(ids) & {r["run_id"] for r in read_rows(dst)}), "already appended (or id clash)"
assert not any("SMOKE" in r["notes"] for r in new), "smoke rows must never be appended"
backup = dst.with_suffix(".csv.bak")
shutil.copyfile(dst, backup)
n = append_rows(dst, new)
after = dst.read_bytes()
assert after.startswith(before), "existing rows were modified"
print(f"appended {n} rows from {src.name}; total {len(read_rows(dst))}; sha {hashlib.sha256(after).hexdigest()[:16]}; backup {backup.name}")
