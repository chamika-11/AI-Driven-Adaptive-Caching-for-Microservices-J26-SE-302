"""Write-up artefacts (R-E12; Addendum M11-E, E4) regenerated from results/results.csv (+ the shift report) with ONE command:

    python scripts/make_artifacts.py            # -> results/artifacts/{T1,T3,T4,T5,T7}*.md|csv, F1,F3,F4,F5,F6*.png, INDEX.md

T2 and F2 come from scripts/make_f2_t2.py (called here), F7 and T7 from scripts/shift_report.py.  Everything is SYNTHETIC.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rlcache.analysis import stats as S  # noqa: E402
from rlcache.analysis.report import load_rows  # noqa: E402

OUT = ROOT / "results" / "artifacts"
OUT.mkdir(parents=True, exist_ok=True)
PY = sys.executable
df = load_rows(ROOT / "results" / "results.csv")
df = df[df.staleness_mode == "harsh"]
CAPS_DQN = (0.01, 0.05, 0.25)
AGENTS = ["dqn:main", "dqn:bandit", "dqn:vanilla", "tabq:qbin", "tabq:bandit"]
produced, missing = [], []


def md_table(t: pd.DataFrame, floatfmt="{:.4f}") -> str:
    cols = list(t.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in t.iterrows():
        lines.append("| " + " | ".join(floatfmt.format(v) if isinstance(v, (float, np.floating)) else str(v)
                                       for v in r) + " |")
    return "\n".join(lines)


def save_table(name: str, t: pd.DataFrame, title: str, note: str = "") -> None:
    t.to_csv(OUT / f"{name}.csv", index=False)
    (OUT / f"{name}.md").write_text(f"# {title}\n\n{md_table(t)}\n\n{note}\n", encoding="utf-8")
    produced.append(f"{name}: {title}")


def test_means(policy, cap, col):
    t = df[(df.split == "test") & (df.capacity_frac == cap) & (df.policy == policy)]
    return t.groupby("seed")[col].mean()


# ---- T1 baseline inventory -----------------------------------------------------------------------------
def t1():
    from rlcache.baselines.policies import eviction_registry, registry
    fam_info = {
        "fixed": ("TTL ladder x placement", "this project (Python)", "45 actions, fixed", 0),
        "random": ("floor", "this project", "uniform over 45 actions", 0),
        "stat_ttl": ("statistics TTL", "this project", "key gap statistic (fit slice), snapped to bucket", 8),
        "pred_ttl": ("predictor TTL", "this project", "stand-in predictor tables", 8),
        "aimd": ("adaptive TTL", "this project", "alpha {60,300}s, beta {0.5,0.25}", 8),
        "place_hash": ("placement rule (post-hoc)", "this project", "fraction {0.10,0.25,0.50} local", 0),
        "place_size": ("placement rule (post-hoc)", "this project", "size percentile {25,50,75}", 0),
        "place_freq": ("placement rule (post-hoc)", "this project", "k {2,3,5} in last 1,000 requests", 8),
        "oracle_ttl": ("BOUND (future knowledge)", "this project", "largest bucket <= time to next write", 0),
        "belady": ("BOUND (future knowledge)", "this project (unit-size objects)", "offline", 0),
        "evict": ("strong eviction (new, E1)", "this project, from the SIEVE / S3-FIFO / LRU / FIFO descriptions",
                  "TTL 3600 s, placement redis|both", 17),
    }
    rows = []
    seen = set()
    for s in registry() + eviction_registry():
        if s.family in seen and s.family not in ("fixed",):
            pass
        info = fam_info.get(s.family, ("", "", "", 0))
        rows.append({"policy": s.name, "family": s.family, "tier/role": info[0], "implementation": info[1],
                     "parameters": info[2], "tuning budget": "none (fixed before evaluation)"
                     + ("; added post-hoc (M6-B)" if s.post_hoc else ""),
                     "per-key metadata bytes (estimate)": info[3]})
    save_table("T1_baseline_inventory", pd.DataFrame(rows), "T1 - baseline inventory",
               "Metadata bytes are estimates (SIEVE: 2 pointers + visited bit; S3-FIFO: freq + queue links; TTL tables: one float per key). "
               "ARC, W-TinyLFU, LeCaR, 2Q and libCacheSim baselines are NOT implemented (Addendum M11-E).")


# ---- T3 head-to-head (from Addendum S1) ---------------------------------------------------------------------
def t3():
    p = ROOT / "results" / "stats_report.json"
    if not p.exists():
        subprocess.run([PY, str(ROOT / "scripts" / "stats_report.py")], cwd=ROOT, check=False)
    d = json.loads(p.read_text(encoding="utf-8"))
    t = pd.DataFrame(d["tests"])[["agent", "cap", "mean_dU", "dz", "p", "p_holm"]]
    t.columns = ["agent", "capacity", "mean dU vs place_size:p25", "Cohen d_z", "Wilcoxon p", "Holm p"]
    save_table("T3_head_to_head", t, "T3 - head-to-head statistics (post-hoc family, Addendum S1)",
               "Test slice, evaluation seeds 0-9, synthetic. Negative dU = agent worse than the size-threshold placement rule.")


# ---- T4 headroom -------------------------------------------------------------------------------------------
def t4():
    rows = []
    for cap in CAPS_DQN:
        base = df[(df.capacity_frac == cap) & (df.policy_class == "heuristic")]
        val = base[base.split == "val"].groupby("policy").utility.mean()
        best = val.idxmax()
        ohr = lambda p: float(test_means(p, cap, "ohr").mean())                # noqa: E731
        stl = lambda p: float(test_means(p, cap, "stale_read_rate").mean())    # noqa: E731
        bel = ohr("belady_ttl_constrained") if len(test_means("belady_ttl_constrained", cap, "ohr")) else float("nan")
        belp = ohr("belady_plain") if len(test_means("belady_plain", cap, "ohr")) else float("nan")
        for ag in ("dqn:main", "dqn:bandit", "tabq:qbin"):
            rows.append({"capacity": cap, "best baseline (by val U)": best, "agent": ag,
                         "OHR best": ohr(best), "OHR agent": ohr(ag), "OHR Belady (TTL-constrained, unit-size)": bel,
                         "OHR Belady plain": belp,
                         "OHR headroom captured": (ohr(ag) - ohr(best)) / (bel - ohr(best)) if bel > ohr(best) else float("nan"),
                         "stale% best": 100 * stl(best), "stale% agent": 100 * stl(ag),
                         "stale reduction vs best (bound = 100%)": (stl(best) - stl(ag)) / stl(best) if stl(best) > 0 else float("nan")})
    save_table("T4_headroom", pd.DataFrame(rows), "T4 - headroom",
               "Belady bounds use unit-size objects and object-count capacity, so they are loose upper bounds on OHR for byte-capacity caches; "
               "negative values mean the agent is WORSE than the best baseline.")


# ---- T5 overhead (measured) ---------------------------------------------------------------------------------
def t5():
    from rlcache.agents import dqn_train as T
    from rlcache.agents.qnet_numpy import NumpyDuelingQ
    from rlcache.baselines.policies import registry
    from rlcache.evaluation import EvalContext, evaluate_sim_policy
    from rlcache.features import FeatureTracker, Normalizer
    ctx = EvalContext.build(0, 0.01, "harsh")
    net = NumpyDuelingQ(obs_dim=19, n_actions=45, hidden=128, seed=0)
    x = np.random.default_rng(0).uniform(size=19).astype(np.float32)
    t0 = time.perf_counter()
    for _ in range(2000):
        net.q_values(x)
    fwd_us = (time.perf_counter() - t0) / 2000 * 1e6
    reg = {s.name: s for s in registry()}

    class Res:                                         # minimal stand-in for DQNResult
        learner, norm = net, Normalizer(ctx.cfg.features)
        diag = {"dueling": True}
    pol = T.GreedyDQNPolicy(Res, ctx)
    spec = reg["place_size:p25"]
    rows = {}
    for label, make in (("place_size:p25 (rule)", lambda: spec.make(ctx)), ("dqn greedy (numpy inference)", lambda: pol)):
        r = evaluate_sim_policy(ctx, spec, "test", policy=make())
        rows[label] = (r["throughput_req_per_s"], r["n_decisions"], r["n_reads"], r["lat_mean_us"])
    (t_rule, nd, nr, lat), (t_dqn, _, _, _) = rows["place_size:p25 (rule)"], rows["dqn greedy (numpy inference)"]
    n_req = ctx.slice_for("test")[1] - ctx.slice_for("test")[0]
    extra_s = n_req / t_dqn - n_req / t_rule
    per_dec_us = max(extra_s, 0.0) / max(nd, 1) * 1e6
    tracker = FeatureTracker(ctx.trace.n_keys, ctx.cfg.features, ctx.predictor, Res.norm)
    state_bytes = 8 * sum(len(v) for v in vars(tracker).values() if isinstance(v, list))     # 8 B per element
    params = sum(w.size for w in net.export_weights().values()) * 4
    t = pd.DataFrame([
        {"item": "numpy forward pass of the 19-128-128-45 dueling network (us)", "value": round(fwd_us, 1)},
        {"item": "full per-decision overhead incl. feature tracking, simulator-measured (us)", "value": round(per_dec_us, 1)},
        {"item": "decisions per 1,000 reads (test slice, 1% capacity, rule policy)", "value": round(1000 * nd / nr, 1)},
        {"item": "amortised overhead per read (us)", "value": round(per_dec_us * nd / nr, 2)},
        {"item": "mean read latency in the model (us), rule policy", "value": round(lat, 1)},
        {"item": "overhead as % of mean read latency (control-plane cost, NOT in the model)", "value": round(100 * per_dec_us * nd / nr / lat, 3)},
        {"item": "network parameters (bytes, float32)", "value": params},
        {"item": "feature-tracker state (bytes, 8 B per list element: per-key tables + request/hit rings + rate bins)", "value": state_bytes},
        {"item": "feature-tracker state per key (bytes)", "value": round(state_bytes / ctx.trace.n_keys, 1)},
        {"item": "training: 300,000 decisions, one core (s), from run notes", "value": "about 500-600"},
    ])
    save_table("T5_overhead", t, "T5 - overhead (measured on this PC)",
               "Pure-Python simulator timings; absolute values depend on the machine. The decision overhead is control-plane cost: it is not added "
               "to the modelled request latency. Metadata is NOT charged against cache capacity (R-E8 / T6 not run).")


# ---- figures ------------------------------------------------------------------------------------------------
def figures():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    # F1 miss-ratio curves (baselines only) --------------------------------------------------------------
    caps = sorted(df[df.split == "test"].capacity_frac.unique())
    show = ["random:45", "fixed:redis/3600s/normal", "fixed:both/3600s/normal", "stat_ttl:median/redis", "place_size:p25",
            "evict:lru/redis/3600s", "evict:sieve/redis/3600s", "evict:s3fifo/redis/3600s",
            "belady_ttl_constrained", "belady_plain"]
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for p in show:
        xs, mu, lo, hi = [], [], [], []
        for c in caps:
            m = 1 - test_means(p, c, "ohr")
            if len(m) >= 5:
                xs.append(100 * c); mu.append(m.mean()); lo.append(m.min()); hi.append(m.max())
        if xs:
            ls = "k--" if p.startswith("belady") else "-"
            ax.plot(xs, mu, ls if ls != "-" else "-o", ms=3, lw=1.2, label=p)
            ax.fill_between(xs, lo, hi, alpha=0.06)
    for ag, mk in (("dqn:main", "s"), ("tabq:qbin", "^")):
        xs = [100 * c for c in CAPS_DQN]
        ax.plot(xs, [1 - test_means(ag, c, "ohr").mean() for c in CAPS_DQN], mk, ms=7, label=ag + " (1/5/25% only)")
    ax.set_xscale("log"); ax.set_xlabel("L2 capacity, % of unique-object footprint"); ax.set_ylabel("miss ratio (1 - OHR; stale hits count as hits)")
    ax.legend(fontsize=6, ncol=2); ax.set_title("F1 miss-ratio curves (synthetic, test slice, seeds 0-9; baselines at all capacities)", fontsize=8)
    fig.tight_layout(); fig.savefig(OUT / "F1_miss_ratio_curves.png", dpi=130); plt.close(fig)
    produced.append("F1_miss_ratio_curves.png: baselines at every capacity present; learned agents only at 1/5/25%")
    # scores (dU vs random) for F3-F6 ------------------------------------------------------------------------
    score = {ag: np.column_stack([test_means(ag, c, "utility").to_numpy() - test_means("random:45", c, "utility").to_numpy()
                                  for c in CAPS_DQN]) for ag in AGENTS}
    fig, ax = plt.subplots(figsize=(6, 3))
    for i, ag in enumerate(AGENTS):
        p, lo, hi = S.stratified_bootstrap_ci(score[ag], n_boot=2000)
        ax.errorbar(p, i, xerr=[[p - lo], [hi - p]], fmt="o", capsize=3)
    ax.set_yticks(range(len(AGENTS))); ax.set_yticklabels(AGENTS, fontsize=7); ax.axvline(0, color="k", lw=0.6)
    ax.set_xlabel("IQM of dU vs random:45 (3 capacities x 10 seeds), 95% stratified bootstrap"); ax.set_title("F3", fontsize=8)
    fig.tight_layout(); fig.savefig(OUT / "F3_iqm_intervals.png", dpi=130); plt.close(fig)
    thr = np.linspace(-0.25, 0.12, 60)
    fig, ax = plt.subplots(figsize=(6, 3.5))
    for ag in AGENTS:
        ax.plot(thr, S.performance_profile(score[ag], thr), label=ag)
    ax.set_xlabel("dU vs random:45 threshold"); ax.set_ylabel("fraction of (seed, capacity) above"); ax.legend(fontsize=6); ax.set_title("F4 performance profiles", fontsize=8)
    fig.tight_layout(); fig.savefig(OUT / "F4_performance_profiles.png", dpi=130); plt.close(fig)
    M = np.array([[0.5 if x == y else S.probability_of_improvement(score[x], score[y]) for y in AGENTS] for x in AGENTS])
    fig, ax = plt.subplots(figsize=(4.8, 4))
    im = ax.imshow(M, vmin=0, vmax=1, cmap="RdBu_r")
    ax.set_xticks(range(len(AGENTS))); ax.set_xticklabels(AGENTS, rotation=45, ha="right", fontsize=6)
    ax.set_yticks(range(len(AGENTS))); ax.set_yticklabels(AGENTS, fontsize=6)
    for i in range(len(AGENTS)):
        for j in range(len(AGENTS)):
            ax.text(j, i, f"{M[i, j]:.2f}", ha="center", va="center", fontsize=6)
    ax.set_title("F5 P(row > column)", fontsize=8); fig.tight_layout(); fig.savefig(OUT / "F5_probability_of_improvement.png", dpi=130); plt.close(fig)
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.2), sharey=False)
    for ax, (j, c) in zip(axes, enumerate(CAPS_DQN)):
        ax.boxplot([score[ag][:, j] for ag in AGENTS]); ax.set_xticklabels([a.replace("dqn:", "d:").replace("tabq:", "t:") for a in AGENTS])
        ax.axhline(0, color="k", lw=0.6); ax.set_title(f"L2 = {c:.0%}", fontsize=8); ax.tick_params(labelsize=6)
    axes[0].set_ylabel("dU vs random:45 (test, 10 seeds)"); fig.suptitle("F6 per-capacity spread", fontsize=8)
    fig.tight_layout(); fig.savefig(OUT / "F6_boxplots.png", dpi=130); plt.close(fig)
    produced.append("F3_iqm_intervals.png, F4_performance_profiles.png, F5_probability_of_improvement.png, F6_boxplots.png (rliable-style, dU vs random)")


def main():
    for step in (t1, t3, t4, t5, figures):
        try:
            step()
        except Exception as e:                                  # noqa: BLE001
            missing.append(f"{step.__name__} FAILED: {e!r}")
    subprocess.run([PY, str(ROOT / "scripts" / "make_f2_t2.py")], cwd=ROOT, check=False, capture_output=True)
    produced.append("T2_harsh_cap*.md/csv and F2_pareto_harsh.png (results/, scripts/make_f2_t2.py)")
    if (ROOT / "results" / "shift").exists():
        r = subprocess.run([PY, str(ROOT / "scripts" / "shift_report.py")], cwd=ROOT, capture_output=True, text=True)
        (OUT / "T7_adaptation.txt").write_text(r.stdout, encoding="utf-8")
        produced.append("T7_adaptation.txt + F7_adaptation.png (scripts/shift_report.py)")
    not_made = [
        ("T6", "metadata-charged re-run of T2 (R-E8) - not run"),
        ("T8", "ablation ladder S0-S5 and arms A-D (R-E9) - out of scope of Addendum M11-E"),
        ("T9", "simulation-vs-deployment agreement - needs the Redis demo (deferred)"),
        ("F8", "latency CDF from a deployment - needs the Redis demo (deferred)"),
        ("F9", "tier-ratio sensitivity - not run"),
        ("F10", "predictor-degradation curve - not run beyond the M7 signal test"),
        ("F11", "training curves - not saved by the evaluation runs (appendix item)"),
    ]
    idx = ["# Artefact index (generated by scripts/make_artifacts.py)\n", "All numbers are SYNTHETIC-workload results. C3 (CartPole) was not met for the "
           "dueling+Double architecture.\n", "## Produced\n"] + [f"* {p}" for p in produced] + ["\n## NOT produced (and why)\n"] + \
          [f"* **{k}** - {v}" for k, v in not_made] + (["\n## Problems while generating\n"] + [f"* {m}" for m in missing] if missing else [])
    (OUT / "INDEX.md").write_text("\n".join(idx) + "\n", encoding="utf-8")
    print("\n".join(idx))


if __name__ == "__main__":
    main()
