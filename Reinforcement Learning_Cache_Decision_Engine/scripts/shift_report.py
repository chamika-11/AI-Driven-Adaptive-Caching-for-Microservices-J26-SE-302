"""Addendum M11-E (E3) report: per-shift metrics (T7), the pre-registered criteria A1 / A2, figure F7.

    python scripts/shift_report.py [--dir results/shift] [--out results/shift_report.json]
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rlcache import shift as SH  # noqa: E402
from rlcache.analysis.signal import paired_bootstrap_ci  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--dir", default="results/shift")
ap.add_argument("--out", default="results/shift_report.json")
ap.add_argument("--fig", default="results/artifacts/F7_adaptation.png")
a = ap.parse_args()

NONLEARNED = ["place_size:p25", "fixed:redis/3600s/normal", "random:45", "stat_ttl:median/redis", "aimd:a60/b0.5",
              "aimd:a300/b0.25", "evict:sieve/redis/3600s", "evict:s3fifo/redis/3600s", "evict:lru/redis/3600s"]
LEARNED = ["dqn:main:frozen", "dqn:main:online", "dqn:bandit:frozen", "dqn:bandit:online"]
A1_REFS = ["place_size:p25", "aimd:a60/b0.5", "evict:sieve/redis/3600s", "evict:s3fifo/redis/3600s"]
PRIMARY = "dqn:main:online"

data = {}                                      # (shift, seed) -> {"meta":..., "series":...}
for f in sorted(Path(a.dir).glob("*.json")):
    d = json.loads(f.read_text(encoding="utf-8"))
    if d["meta"].get("smoke"):
        continue
    data[(d["meta"]["shift"], d["meta"]["seed"])] = d
shifts = [s for s in SH.SHIFTS if any(k[0] == s for k in data)]
if not shifts:
    sys.exit("no (non-smoke) shift results found")

rows, per = [], {}                              # per[(shift, policy)] -> dict of arrays over seeds
for sh in shifts:
    seeds = sorted(k[1] for k in data if k[0] == sh)
    for pol in NONLEARNED + LEARNED:
        vals = {"h_pre": [], "dip": [], "area": [], "rec": [], "spike": [], "regret": [], "ttl_b": [], "ttl_a": []}
        for sd in seeds:
            d = data[(sh, sd)]
            m, ser = d["meta"], d["series"]
            mm = SH.shift_metrics(ser[pol], m["t_star"], m["test_start"], m["window"])
            reg = SH.cumulative_regret(ser[pol], [ser[n] for n in NONLEARNED], m["t_star"], m["test_start"], m["window"])
            for k, v in (("h_pre", mm.h_pre), ("dip", mm.dip_depth), ("area", mm.area_under_dip),
                         ("rec", mm.recovery_requests), ("spike", mm.stale_spike), ("regret", reg),
                         ("ttl_b", mm.ttl_before), ("ttl_a", mm.ttl_after)):
                vals[k].append(v)
        per[(sh, pol)] = {k: np.array(v, float) for k, v in vals.items()}
        rows.append((sh, pol, len(seeds)))

print("=== T7: adaptation metrics, mean over seeds (shift suite, 1% capacity, SYNTHETIC) ===")
print(f"{'shift':<9}{'policy':<27}{'h_pre':>7}{'dip pp':>8}{'area':>9}{'rec(req)':>10}{'spike':>8}{'regret':>8}{'TTL b->a':>14}")
out = {"T7": [], "A1": {}, "A2": {}}
for sh, pol, n in rows:
    v = per[(sh, pol)]
    rec = v["rec"]
    rtxt = f"{np.nanmean(rec):.0f}" + (f"*{int(np.isnan(rec).sum())}" if np.isnan(rec).any() else "")
    print(f"{sh:<9}{pol:<27}{np.nanmean(v['h_pre']):7.3f}{np.nanmean(v['dip']):8.2f}{np.nanmean(v['area']):9.0f}"
          f"{rtxt:>10}{np.nanmean(v['spike']):8.3f}{np.nanmean(v['regret']):8.3f}"
          f"{np.nanmedian(v['ttl_b']):8.0f}->{np.nanmedian(v['ttl_a']):<5.0f}")
    out["T7"].append({"shift": sh, "policy": pol, "n_seeds": n,
                      **{k: float(np.nanmean(x)) for k, x in v.items()}})
print("(* = number of seeds where recovery was censored)")

print(f"\n=== A1: {PRIMARY} cumulative regret minus reference regret (paired by seed, 95% CI) ===")
supported_shifts = []
for sh in shifts:
    ok_all, line = True, []
    for ref in A1_REFS:
        d = per[(sh, PRIMARY)]["regret"] - per[(sh, ref)]["regret"]
        lo, hi = paired_bootstrap_ci(d, n_boot=10_000)
        line.append(f"{ref.split('/')[0]}: {d.mean():+.3f} [{lo:+.3f},{hi:+.3f}]")
        ok_all &= bool(hi < 0)
        out["A1"][f"{sh}|{ref}"] = [float(d.mean()), float(lo), float(hi)]
    steady = float(np.nanmean(per[(sh, PRIMARY)]["h_pre"]) - np.nanmean(per[(sh, "place_size:p25")]["h_pre"]))
    ok_all &= steady >= -0.01
    print(f"  {sh:<8} " + " | ".join(line) + f" | steady-state gap vs place_size {steady:+.3f}  -> {'YES' if ok_all else 'no'}")
    if ok_all:
        supported_shifts.append(sh)
a1 = len(supported_shifts) >= 2
print(f"A1 (needs >= 2 of 4 shifts): {'SUPPORTED' if a1 else 'NOT SUPPORTED'}  (shifts passing: {supported_shifts})")
out["A1_verdict"] = "SUPPORTED" if a1 else "NOT SUPPORTED"

if "write10" in shifts:
    v = per[("write10", "dqn:main:frozen")]
    d = v["ttl_a"] - v["ttl_b"]
    lo, hi = paired_bootstrap_ci(d, n_boot=10_000)
    a2 = bool(hi < 0)
    print(f"\nA2 (TTL action does work), dqn:main frozen, write x10: median TTL after - before = {d.mean():+.1f} s "
          f"[{lo:+.1f},{hi:+.1f}] -> {'YES' if a2 else 'no'}")
    out["A2"] = {"frozen": [float(d.mean()), float(lo), float(hi)], "verdict": a2}
    v = per[("write10", PRIMARY)]
    d = v["ttl_a"] - v["ttl_b"]
    lo, hi = paired_bootstrap_ci(d, n_boot=10_000)
    print(f"   (online variant: {d.mean():+.1f} s [{lo:+.1f},{hi:+.1f}])")
    out["A2"]["online"] = [float(d.mean()), float(lo), float(hi)]
Path(a.out).write_text(json.dumps(out, indent=1), encoding="utf-8")

# ---- F7: hit-ratio series per shift ----------------------------------------------------------------------
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    show = ["place_size:p25", "aimd:a60/b0.5", "evict:sieve/redis/3600s", "evict:s3fifo/redis/3600s",
            "dqn:main:frozen", "dqn:main:online", "dqn:bandit:online"]
    fig, axes = plt.subplots(len(shifts), 1, figsize=(9, 2.6 * len(shifts)), sharex=True)
    axes = np.atleast_1d(axes)
    for ax, sh in zip(axes, shifts):
        seeds = sorted(k[1] for k in data if k[0] == sh)
        for pol in show:
            arr = np.array([data[(sh, sd)]["series"][pol]["hit_ratio"] for sd in seeds], float)
            mu, lo, hi = np.nanmean(arr, 0), np.nanpercentile(arr, 10, 0), np.nanpercentile(arr, 90, 0)
            x = np.arange(len(mu))
            ax.plot(x, mu, lw=1.6 if pol.startswith("dqn") else 1.0, label=pol)
            ax.fill_between(x, lo, hi, alpha=0.08)
        m = data[(sh, seeds[0])]["meta"]
        ax.axvline((m["t_star"] - m["test_start"]) / m["window"], color="k", ls="--", lw=0.8)
        ax.set_ylabel("hit ratio")
        ax.set_title(f"shift: {sh}", fontsize=9, loc="left")
    axes[-1].set_xlabel("window (5,000 requests) since the start of the test slice; dashed = shift")
    axes[0].legend(fontsize=6, ncol=2)
    Path(a.fig).parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(a.fig, dpi=130)
    print("wrote", a.fig)
except Exception as e:                                    # noqa: BLE001
    print("figure skipped:", e)
