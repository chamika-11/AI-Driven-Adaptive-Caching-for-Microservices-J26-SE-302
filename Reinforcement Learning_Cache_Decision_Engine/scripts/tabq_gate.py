"""M8 development gate (pre-registered: docs/PREREGISTRATION.md, Addendum M8 + Amendment M8-a).

    python scripts/tabq_gate.py          # dev seeds 100-109, caps 1/5/25%, variants qbin/ewidth/bandit

Gate: U(tabq:qbin, greedy, validation slice) - U(random:45), paired by seed.
Writes results/tabq_dev.csv (schema rows) and results/tabq_dev.json.  Dev seeds only.
"""
import json
import sys
import time
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import numpy as np  # noqa: E402

from rlcache.agents.tabular_q import GreedyTabularPolicy, train_tabular  # noqa: E402
from rlcache.analysis.signal import paired_bootstrap_ci  # noqa: E402
from rlcache.baselines.policies import Spec, registry  # noqa: E402
from rlcache.evaluation import EvalContext, evaluate, evaluate_sim_policy  # noqa: E402
from rlcache.results_schema import append_rows  # noqa: E402

VARIANTS = {"qbin": ("qbin", None), "ewidth": ("ewidth", None), "bandit": ("qbin", 0.0)}
REF = ("random:45", "fixed:redis/3600s/normal", "place_size:p25")


def tabq_rows(ctx: EvalContext, variant: str, splits=("val", "test")) -> list[dict]:
    kind, gamma = VARIANTS[variant]
    res = train_tabular(ctx, kind, gamma)
    rows = []
    for split in splits:
        pol = GreedyTabularPolicy(res, ctx)
        spec = Spec(f"tabq:{variant}", "tabular_q", "learned", lambda c, p=pol: p)
        r = evaluate_sim_policy(ctx, spec, split, policy=pol)
        a = res.agent.n_sa.sum(axis=1)
        r["notes"] = (f"tabular_q variant={variant} gamma={res.gamma} decisions={res.decisions} "
                      f"epochs={res.epochs} coverage_train={res.agent.coverage():.3f} "
                      f"unvisited_decision_share={pol.unvisited_decision_share():.3f} "
                      f"mean_abs_td={res.td_abs_mean:.4f}")
        rows.append(r)
    return rows


def _job(args):
    seed, cap, variants = args
    ctx = EvalContext.build(seed, cap, "harsh")
    rows = []
    for v in variants:
        rows += tabq_rows(ctx, v)
    reg = {s.name: s for s in registry()}
    for name in REF:
        for split in ("val", "test"):
            rows.append(evaluate(ctx, reg[name], split))
    return rows


def main():
    t0 = time.time()
    seeds = list(range(100, 110))
    caps = [0.01, 0.05, 0.25]
    jobs = [(s, c, list(VARIANTS)) for s in seeds for c in caps]
    with Pool(10) as pool:
        out = [r for rows in pool.imap_unordered(_job, jobs) for r in rows]
    path = Path("results/tabq_dev.csv")
    if path.exists():
        path.unlink()
    append_rows(path, out)
    print(f"{len(out)} rows in {time.time()-t0:.0f}s")

    def U(policy, cap, split="val"):
        d = {r["seed"]: r["utility"] for r in out
             if r["policy"] == policy and r["capacity_frac"] == cap and r["split"] == split}
        return np.array([d[s] for s in seeds])

    def M(policy, cap, key, split="val"):
        return float(np.mean([r[key] for r in out if r["policy"] == policy
                              and r["capacity_frac"] == cap and r["split"] == split]))

    summary = {}
    print("\n## GATE: U(tabq:qbin) - U(random:45), validation slice, paired by seed (dev seeds 100-109)")
    print(f"{'cap':>5}{'mean dU':>10}{'95% CI':>22}{'pos':>6}  PASS")
    for cap in caps:
        d = U("tabq:qbin", cap) - U("random:45", cap)
        lo, hi = paired_bootstrap_ci(d)
        ok = bool(d.mean() > 0 and lo > 0 and (d > 0).sum() >= 8)
        summary[f"gate@{cap}"] = {"mean_dU": float(d.mean()), "ci": [lo, hi], "n_pos": int((d > 0).sum()),
                                  "pass": ok}
        print(f"{cap:5.2f}{d.mean():10.4f}{'[%.4f, %.4f]' % (lo, hi):>22}{int((d > 0).sum()):>4}/10  {ok}")
    print("\n## context (validation slice, seed means): U / OHR / stale%")
    print(f"{'cap':>5} {'policy':<26}{'U':>8}{'OHR':>8}{'stale%':>8}")
    for cap in caps:
        for p in ("tabq:qbin", "tabq:ewidth", "tabq:bandit") + REF:
            print(f"{cap:5.2f} {p:<26}{M(p, cap, 'utility'):8.4f}{M(p, cap, 'ohr'):8.4f}"
                  f"{100*M(p, cap, 'stale_read_rate'):8.3f}")
            summary[f"{p}@{cap}"] = {"U": M(p, cap, "utility"), "ohr": M(p, cap, "ohr"),
                                      "stale": M(p, cap, "stale_read_rate")}
    Path("results/tabq_dev.json").write_text(json.dumps(summary, indent=1))
    print(f"\n{time.time()-t0:.0f}s total")


if __name__ == "__main__":
    main()
