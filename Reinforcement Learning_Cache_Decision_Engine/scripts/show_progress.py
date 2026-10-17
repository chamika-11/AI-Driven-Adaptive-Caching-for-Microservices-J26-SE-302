"""Progress of the M9-e repair run: units finished, rough time left.   python scripts/show_progress.py"""
import csv, re, time
from pathlib import Path

log = Path("results/dqn_repair_stdout2.log")
rows = list(csv.DictReader(open("results/dqn_repair_dev.csv", encoding="utf-8")))
done = {(r["seed"], r["capacity_frac"]) for r in rows if r["policy"].startswith("dqn")}
total = 30
started = log.stat().st_ctime
new = [m for m in re.findall(r"seed \d+ cap [\d.]+: \+(\d+) rows \((\d+)s\)", log.read_text()) if int(m[0]) > 0]
print(f"units finished: {len(done)}/{total}   (this session: {len(new)} new of 10)")
el = time.time() - started
print(f"elapsed this session: {el/60:.0f} min")
if new:
    per = int(new[-1][1]) / len(new)
    print(f"~{max(0, (10-len(new))) * per / 5 / 60:.0f} min left (rough)")
else:
    print("first units still training (each unit = 3 agents x ~9 min; expect first results after ~25-30 min)")
