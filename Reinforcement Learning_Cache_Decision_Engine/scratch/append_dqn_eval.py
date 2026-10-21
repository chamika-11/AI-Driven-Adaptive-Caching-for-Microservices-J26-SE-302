import csv, hashlib, shutil, sys
from pathlib import Path
sys.path.insert(0, "src")
from rlcache.results_schema import append_rows, read_rows

new = read_rows("results/dqn_eval.csv")
ids = [r["run_id"] for r in new]
assert len(ids) == len(set(ids)) == 180, len(ids)
assert all(r["family"] == "dqn" and r["policy_class"] == "learned" and int(r["seed"]) < 100 for r in new)

canon = Path(r"E:\Research\New folder\results\results.csv")
mirror = Path("results/results.csv")
before = canon.read_bytes()
assert hashlib.sha256(before).hexdigest() == hashlib.sha256(mirror.read_bytes()).hexdigest()
old = read_rows(canon)
assert not (set(ids) & {r["run_id"] for r in old}), "already appended"
n = append_rows(canon, new)
after = canon.read_bytes()
assert after.startswith(before), "existing rows were modified"       # spent rows byte-identical
shutil.copyfile(canon, mirror)
print("appended", n, "rows; total", len(read_rows(canon)), "sha", hashlib.sha256(after).hexdigest()[:16])
