"""M9 cache experiments (pre-registered: docs/PREREGISTRATION.md, Addendum M9).

    python scripts/run_dqn.py --stage dev  --backend torch --procs 2     # gate, dev seeds 100-104
    python scripts/run_dqn.py --stage eval --backend torch --procs 2     # ONCE, seeds 0-9

Run ONLY after scripts/dqn_checks.py (C1, C2) and scripts/dqn_cartpole.py (C3) have passed.
Resumable: rows already in --out are skipped.  Prints the SHA-256 of the code it runs.
Hyper-parameters are the frozen DQNConfig defaults; do not edit them.
"""
import argparse
import csv
import hashlib
import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

VARIANTS = {"dqn": 0.95, "dqn_bandit": 0.0, "dqn_vanilla": 0.95}      # Amendment M9-d
# architecture flags per variant: (dueling, double).  dqn_vanilla is the ablation arm.
ARCH = {"dqn": (True, True), "dqn_bandit": (True, True), "dqn_vanilla": (False, False),
        "dqn_perkey": (True, True)}
# Amendment M9-e: repair arm, NOT in the default variant list (so eval/dev defaults are unchanged)
EXTRA_VARIANTS = {"dqn_perkey": 0.95}
SUCCESSOR = {"dqn_perkey": "same_key"}         # every other variant keeps the D-9 successor "any"
CAPS = (0.01, 0.05, 0.25)
REFS = ("random:45", "fixed:redis/3600s/normal", "place_size:p25")


def code_hash() -> str:
    h = hashlib.sha256()
    for p in sorted((ROOT / "src").rglob("*.py")) + sorted((ROOT / "scripts").glob("*.py")):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()[:16]


def make_learner(backend: str, seed: int, variant: str = "dqn"):
    from rlcache.config import DQNConfig
    c = DQNConfig()
    dueling, double = ARCH[variant]
    kw = dict(obs_dim=19, n_actions=45, hidden=c.hidden, seed=seed, lr=c.lr, dueling=dueling,
              double=double, max_grad_norm=c.max_grad_norm)
    if backend == "torch":
        from rlcache.agents.dqn_torch import TorchLearner
        return TorchLearner(**kw)
    from rlcache.agents.qnet_numpy import NumpyDuelingQ
    return NumpyDuelingQ(**kw)


def dqn_rows(ctx, variant: str, backend: str, ckpt_dir: Path | None, decisions=None,
             suffix: str = "", splits=("val", "test")) -> list[dict]:
    from rlcache.agents import dqn_train as T
    from rlcache.baselines.policies import Spec
    from rlcache.config import DQNConfig
    from rlcache.evaluation import evaluate_sim_policy

    gamma = {**VARIANTS, **EXTRA_VARIANTS}[variant]
    t0 = time.time()
    cfg = DQNConfig()
    if decisions:                                   # SMOKE TEST ONLY - never used for results
        import dataclasses
        cfg = dataclasses.replace(cfg, total_decisions=decisions, learning_starts=max(decisions // 5, 200),
                                  buffer_size=max(decisions * 2, 2000))
    succ = SUCCESSOR.get(variant, "any")
    res = T.train_dqn(ctx, make_learner(backend, ctx.seed, variant), cfg, gamma=gamma,
                      calib_requests=40_000 if not decisions else 4_000, successor=succ)
    secs = time.time() - t0
    if ckpt_dir is not None:
        ckpt_dir.mkdir(parents=True, exist_ok=True)
        T.save_checkpoint(ckpt_dir / f"{variant}{suffix}_cap{ctx.capacity_frac}_s{ctx.seed}.npz", res,
                          {"seed": ctx.seed, "capacity": ctx.capacity_frac, "backend": backend})
    last = res.curve[-1] if res.curve else (0, float("nan"), float("nan"), float("nan"), float("nan"))
    rows = []
    for split in splits:
        pol = T.GreedyDQNPolicy(res, ctx)
        spec = Spec(("dqn:main" if variant == "dqn" else f"dqn:{variant[4:]}") + suffix, "dqn", "learned",
                    lambda c, p=pol: p, eviction=ctx.cfg.cache.base_eviction)
        r = evaluate_sim_policy(ctx, spec, split, policy=pol)
        r["notes"] = (("SMOKE-TEST " if decisions else "") + f"dqn variant={variant} gamma={gamma} backend={backend} decisions={res.decisions} "
                      f"epochs={res.epochs} grad_steps={res.gradient_steps} train_s={secs:.0f} "
                      f"successor={succ} dropped_tail={res.diag.get('dropped_tail')} emitted={res.diag.get('emitted')} "
                      f"last_loss={last[1]:.5f} last_Qmean={last[2]:.3f} last_Qmax={last[3]:.3f} "
                      f"base_eviction={ctx.cfg.cache.base_eviction} code={code_hash()}")
        rows.append(r)
    return rows


def _job(args):
    seed, cap, variants, backend, ckpt, with_refs, skip, decisions = args
    from rlcache.baselines.policies import registry
    from rlcache.evaluation import EvalContext, evaluate
    ctx = EvalContext.build(seed, cap, "harsh")
    rows = []
    for v in variants:
        name = "dqn:main" if v == "dqn" else f"dqn:{v[4:]}"
        if all(f"dqn|{name}|harsh|cap{cap}|{sp}|s{seed}" in skip for sp in ("val", "test")):
            continue
        rows += dqn_rows(ctx, v, backend, Path(ckpt) if ckpt else None, decisions)
    if with_refs:
        reg = {s.name: s for s in registry()}
        for n in REFS:
            for sp in ("val", "test"):
                rid = f"{reg[n].family}|{n}|harsh|cap{cap}|{sp}|s{seed}"
                if rid not in skip:
                    rows.append(evaluate(ctx, reg[n], sp))
    return seed, cap, rows


def gate_report(rows: list[dict], seeds: list[int], out_json: Path, tabq_csv: Path | None,
                caps=CAPS):
    import numpy as np
    from rlcache.analysis.signal import paired_bootstrap_ci

    def U(policy, cap, split="val"):
        d = {r["seed"]: float(r["utility"]) for r in rows
             if r["policy"] == policy and r["capacity_frac"] == cap and r["split"] == split}
        return np.array([d[s] for s in seeds if s in d])

    tabq = []
    if tabq_csv and tabq_csv.exists():
        with open(tabq_csv, newline="", encoding="utf-8") as fh:
            tabq = [r for r in csv.DictReader(fh) if r["split"] == "val"]
    summary, need = {}, max(4, int(np.ceil(0.8 * len(seeds))))
    print(f"\n## GATE: U(dqn:main) - U(random:45), validation slice, paired by seed "
          f"({len(seeds)} dev seeds; need > 0 in >= {need})")
    print(f"{'cap':>5}{'mean dU':>10}{'95% CI':>22}{'pos':>6}  PASS   collapse(dU<-0.05)")
    for cap in caps:
        d = U("dqn:main", cap) - U("random:45", cap)
        lo, hi = paired_bootstrap_ci(d)
        ok = bool(d.mean() > 0 and lo > 0 and (d > 0).sum() >= need)
        summary[f"gate@{cap}"] = {"mean_dU": float(d.mean()), "ci": [lo, hi], "n_pos": int((d > 0).sum()),
                                  "n": int(len(d)), "pass": ok, "collapse": bool(d.mean() < -0.05)}
        print(f"{cap:5.2f}{d.mean():10.4f}{'[%.4f, %.4f]' % (lo, hi):>22}{int((d > 0).sum()):>4}/{len(d)}"
              f"  {str(ok):<6} {bool(d.mean() < -0.05)}")
    for abl in ("dqn:bandit", "dqn:vanilla"):
        print(f"\n## ablation (does NOT change the verdict): U({abl}) - U(random:45), validation slice")
        for cap in caps:
            if not len(U(abl, cap)):
                continue
            d = U(abl, cap) - U("random:45", cap)
            lo, hi = paired_bootstrap_ci(d)
            ok = bool(d.mean() > 0 and lo > 0 and (d > 0).sum() >= need)
            summary[f"ablation[{abl}]@{cap}"] = {"mean_dU": float(d.mean()), "ci": [lo, hi],
                                                  "n_pos": int((d > 0).sum()), "criterion_met": ok}
            print(f"{cap:5.2f}{d.mean():10.4f}{'[%.4f, %.4f]' % (lo, hi):>22}{int((d > 0).sum()):>4}/{len(d)}"
                  f"  criterion met: {ok}")
    g1, g5, g25 = (summary.get(f"gate@{c}", {}).get("pass", False) for c in CAPS)
    verdict = "PASS" if g1 else ("PARTIAL" if (g5 and g25) else "FAIL")
    print(f"\nPRE-REGISTERED VERDICT: {verdict}   (PASS: holds at 1%; PARTIAL: fails at 1% but holds at 5% "
          f"and 25%; FAIL otherwise -> no evaluation-seed run)")
    summary["verdict"] = verdict
    print("\n## context (validation slice, seed means): U / OHR / stale%")
    print(f"{'cap':>5} {'policy':<26}{'U':>8}{'OHR':>8}{'stale%':>8}")
    own = {r["policy"] for r in rows}
    names = list(dict.fromkeys(["dqn:main", "dqn:bandit", "dqn:vanilla", *REFS] + sorted({r["policy"] for r in tabq})))
    for cap in caps:
        for p in names:
            pool_ = rows if p in own else tabq              # this run's rows win; tabq only if absent
            src = [r for r in pool_ if r["policy"] == p and float(r["capacity_frac"]) == cap
                   and r["split"] == "val"]
            if not src:
                continue
            m = lambda k: float(np.mean([float(r[k]) for r in src]))      # noqa: E731
            print(f"{cap:5.2f} {p:<26}{m('utility'):8.4f}{m('ohr'):8.4f}{100*m('stale_read_rate'):8.3f}")
            summary[f"{p}@{cap}"] = {"U": m("utility"), "ohr": m("ohr"), "stale": m("stale_read_rate")}
    out_json.write_text(json.dumps(summary, indent=1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=("dev", "eval"), required=True)
    ap.add_argument("--backend", choices=("torch", "numpy"), default="torch")
    ap.add_argument("--procs", type=int, default=2)
    ap.add_argument("--out", default=None)
    ap.add_argument("--ckpt", default="results/dqn_ckpt")
    ap.add_argument("--tabq-csv", default="results/tabq_dev.csv")
    ap.add_argument("--seeds", type=int, nargs="+", default=None)
    ap.add_argument("--capacities", type=float, nargs="+", default=list(CAPS))
    ap.add_argument("--variants", nargs="+", default=list(VARIANTS))
    ap.add_argument("--decisions", type=int, default=None,
                    help="SMOKE TEST ONLY: shorten training; rows are tagged and not results")
    a = ap.parse_args()
    if a.decisions and a.stage == "eval":
        sys.exit("--decisions is for smoke tests; it cannot be used with the evaluation stage")

    seeds = a.seeds or (list(range(100, 105)) if a.stage == "dev" else list(range(10)))
    if a.stage == "dev" and min(seeds) < 100:
        sys.exit("dev stage uses development seeds (>= 100) only")
    if a.stage == "eval" and max(seeds) >= 100:
        sys.exit("eval stage uses evaluation seeds 0-9 only")
    out = Path(a.out or ("results/dqn_dev.csv" if a.stage == "dev" else "results/dqn_eval.csv"))
    print(f"code hash {code_hash()}  stage={a.stage} backend={a.backend} procs={a.procs}", flush=True)
    existing = set()
    if out.exists():
        with open(out, newline="", encoding="utf-8") as fh:
            existing = {r["run_id"] for r in csv.DictReader(fh)}
    jobs = [(s, c, a.variants, a.backend, a.ckpt, a.stage == "dev", existing, a.decisions)
            for s in seeds for c in a.capacities]
    from rlcache.results_schema import append_rows
    t0, n = time.time(), 0
    ctx = mp.get_context("spawn")
    with ctx.Pool(min(a.procs, len(jobs))) as pool:
        for seed, cap, rows in pool.imap_unordered(_job, jobs):
            n += append_rows(out, rows)
            print(f"seed {seed} cap {cap}: +{len(rows)} rows ({time.time()-t0:.0f}s)", flush=True)
    print(f"wrote {n} new rows to {out} in {time.time()-t0:.0f}s")
    if a.stage == "dev":
        with open(out, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        for r in rows:
            r["seed"] = int(r["seed"])
            r["capacity_frac"] = float(r["capacity_frac"])
        gate_report(rows, seeds, out.with_suffix(".json"), Path(a.tabq_csv), tuple(a.capacities))


if __name__ == "__main__":
    main()
