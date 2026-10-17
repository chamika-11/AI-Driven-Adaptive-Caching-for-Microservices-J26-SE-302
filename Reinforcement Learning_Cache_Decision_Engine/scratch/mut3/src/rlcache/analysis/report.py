"""T2 (primary results table) and F2 (hit-ratio / stale-read Pareto figure) from results.csv.

Everything is generated from the CSV only (R-E12).  Cross-seed summaries here are mean and sample
standard deviation over evaluation seeds; the rliable IQM / stratified-bootstrap analysis is M11
and is deliberately not faked here.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .pareto import delta_ohr, envelope, pareto_mask

NUMERIC = ["seed", "capacity_frac", "l1_frac", "w_stale", "n_reads", "n_fresh", "n_stale", "n_miss",
           "n_decisions", "ohr", "bhr", "stale_read_rate", "stale_given_hit", "stale_age_mean_s",
           "stale_age_p95_s", "backend_per_1k_reads", "lat_mean_us", "lat_p50_us", "lat_p95_us",
           "lat_p99_us", "lat_p999_us", "cap_evictions_per_1k", "ttl_expirations_per_1k",
           "ttl_median_s", "over_ttl_frac", "ttl_mae_s", "share_local", "share_redis", "share_both",
           "action_entropy_norm", "utility", "throughput_req_per_s"]

T2_COLUMNS = [("ohr", "OHR", 3), ("bhr", "BHR", 3), ("stale_read_rate", "stale reads %", 2),
              ("stale_given_hit", "stale|hit", 3), ("backend_per_1k_reads", "backend /1k", 1),
              ("lat_mean_us", "lat mean µs", 0), ("lat_p95_us", "p95 µs", 0), ("lat_p99_us", "p99 µs", 0),
              ("cap_evictions_per_1k", "evict /1k", 1), ("ttl_expirations_per_1k", "expire /1k", 1),
              ("utility", "U (sel. only)", 3)]


def load_rows(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    for c in NUMERIC:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def best_by_val(df: pd.DataFrame, arm: str, capacity: float) -> dict[str, str]:
    """Per heuristic family: the policy with the highest MEAN validation utility (M6-3)."""
    v = df[(df.split == "val") & (df.staleness_mode == arm) & (df.capacity_frac == capacity)
           & (df.policy_class == "heuristic")]
    out = {}
    for fam, g in v.groupby("family"):
        out[fam] = g.groupby("policy").utility.mean().idxmax()
    return out


def _slice(df, split, arm, capacity):
    return df[(df.split == split) & (df.staleness_mode == arm) & (df.capacity_frac == capacity)]


def policy_means(df: pd.DataFrame, arm: str, capacity: float, split: str = "test") -> pd.DataFrame:
    g = _slice(df, split, arm, capacity).groupby(["policy", "family", "policy_class"])
    out = g[["ohr", "stale_read_rate"]].mean().reset_index()
    out["n_seeds"] = g.seed.nunique().values
    return out


def t2_table(df: pd.DataFrame, arm: str, capacity: float) -> pd.DataFrame:
    """Rows: validation-selected policy of each heuristic family, plus random and the bounds."""
    sel = best_by_val(df, arm, capacity)
    test = _slice(df, "test", arm, capacity)
    rows = []
    for fam, pol in sorted(sel.items()):
        rows.append((f"{fam} -> {pol}", "heuristic", test[test.policy == pol]))
    for pol in sorted(test[test.policy_class == "bound"].policy.unique()):
        rows.append((pol, "bound", test[test.policy == pol]))
    out = []
    for label, cls, g in rows:
        if g.empty:
            continue
        r = {"policy": label, "class": cls, "seeds": g.seed.nunique()}
        for col, name, _ in T2_COLUMNS:
            r[name] = g[col].mean()
            r[name + " sd"] = g[col].std(ddof=1) if len(g) > 1 else 0.0
        out.append(r)
    return pd.DataFrame(out)


def t2_markdown(t: pd.DataFrame, title: str) -> str:
    cols = [name for _, name, _ in T2_COLUMNS]
    dec = {name: d for _, name, d in T2_COLUMNS}
    lines = [f"### {title}", "",
             "| policy | class | seeds | " + " | ".join(cols) + " |",
             "|---|---|---:|" + "---:|" * len(cols)]
    for _, r in t.iterrows():
        cells = []
        for c in cols:
            v, sd = r[c], r[c + " sd"]
            if c == "stale reads %":
                v, sd = 100 * r["stale reads %"], 100 * r["stale reads % sd"]
            cells.append("n/a" if pd.isna(v) else f"{v:.{dec[c]}f} ± {0 if pd.isna(sd) else sd:.{dec[c]}f}")
        lines.append(f"| {r['policy']} | {r['class']} | {int(r['seeds'])} | " + " | ".join(cells) + " |")
    lines += ["", "Mean ± sample sd over evaluation seeds (test split, warm-up excluded). Selection of the "
              "policy within a family uses the validation split only. IQM / bootstrap CIs: M11."]
    return "\n".join(lines)


def frontier_summary(df: pd.DataFrame, arm: str, capacity: float) -> dict:
    """Frontier on seed-averaged points (non-bound heuristics) and its concave envelope."""
    pm = policy_means(df, arm, capacity)
    base = pm[pm.policy_class == "heuristic"]
    if base.empty:
        return {}
    s, h = base.stale_read_rate.to_numpy(), base.ohr.to_numpy()
    mask = pareto_mask(s, h)
    env = envelope(s, h)
    return {
        "arm": arm, "capacity_frac": capacity, "n_policies": int(len(base)),
        "non_dominated": base[mask].sort_values("stale_read_rate")[["policy", "stale_read_rate", "ohr"]]
        .to_dict("records"),
        "envelope": env.tolist(),
        "bounds": pm[pm.policy_class == "bound"][["policy", "stale_read_rate", "ohr"]].to_dict("records"),
    }


def paired_delta(df: pd.DataFrame, policy: str, arm: str, capacity: float) -> pd.DataFrame:
    """Primary statistic of the pre-registration (M6-4) for one policy, per seed: ΔOHR against the
    concave envelope of the OTHER non-bound policies of that seed."""
    t = _slice(df, "test", arm, capacity)
    rows = []
    for seed, g in t.groupby("seed"):
        pt = g[g.policy == policy]
        others = g[(g.policy != policy) & (g.policy_class == "heuristic")]
        if pt.empty or others.empty:
            continue
        env = envelope(others.stale_read_rate.to_numpy(), others.ohr.to_numpy())
        d, beyond = delta_ohr((float(pt.stale_read_rate.iloc[0]), float(pt.ohr.iloc[0])), env)
        rows.append({"seed": seed, "delta_ohr": d, "beyond_frontier": beyond})
    return pd.DataFrame(rows)


def f2_figure(df: pd.DataFrame, arm: str, capacities: list[float], out_path: str | Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fams = ["fixed", "random", "stat_ttl", "pred_ttl", "aimd"]
    colors = dict(zip(fams, ["#4c72b0", "#8c8c8c", "#55a868", "#c44e52", "#8172b2"]))
    fig, axes = plt.subplots(1, len(capacities), figsize=(5.2 * len(capacities), 4.4), squeeze=False)
    for ax, cap in zip(axes[0], capacities):
        pm = policy_means(df, arm, cap)
        if pm.empty:
            ax.set_title(f"L2 = {cap:.0%} (no data)")
            continue
        for fam in fams:
            g = pm[(pm.family == fam) & (pm.policy_class == "heuristic")]
            if len(g):
                ax.scatter(100 * g.stale_read_rate, g.ohr, s=26, c=colors[fam], label=fam, alpha=.85)
        base = pm[pm.policy_class == "heuristic"]
        mask = pareto_mask(base.stale_read_rate.to_numpy(), base.ohr.to_numpy())
        step = base[mask].sort_values("stale_read_rate")
        ax.step(100 * step.stale_read_rate, step.ohr, where="post", c="k", lw=1.0, label="step frontier")
        env = envelope(base.stale_read_rate.to_numpy(), base.ohr.to_numpy())
        if len(env):
            ax.plot(100 * env[:, 0], env[:, 1], "k--", lw=1.0, label="concave envelope")
        b = pm[pm.policy_class == "bound"]
        for _, r in b.iterrows():
            ax.scatter(100 * r.stale_read_rate, r.ohr, marker="D", facecolors="none", edgecolors="r", s=48)
            ax.annotate(r.policy.replace("zerostale_oracle_ttl:", "oracle-TTL ")
                        .replace("belady_ttl_constrained", "Belady-TTL").replace("belady_plain", "Belady"),
                        (100 * r.stale_read_rate, r.ohr), fontsize=6, xytext=(3, 3),
                        textcoords="offset points")
        ax.set_xlabel("stale-read rate (% of reads)")
        ax.set_ylabel("object hit ratio")
        ax.set_title(f"L2 = {cap:.0%} of footprint, staleness={arm}\n(test split, mean of seeds; synthetic)",
                     fontsize=9)
        ax.grid(alpha=.25)
    axes[0][0].legend(fontsize=7, loc="lower right")
    fig.tight_layout()
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=140)
    plt.close(fig)


def write_reports(results_csv: str | Path, out_dir: str | Path, arm: str,
                  capacities: list[float]) -> list[Path]:
    df = load_rows(results_csv)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for cap in capacities:
        t = t2_table(df, arm, cap)
        if t.empty:
            continue
        md = out / f"T2_{arm}_cap{cap}.md"
        md.write_text(t2_markdown(t, f"T2 — {arm}, L2 = {cap:.0%} of footprint (synthetic, test split)"),
                      encoding="utf-8")
        csv = out / f"T2_{arm}_cap{cap}.csv"
        t.to_csv(csv, index=False)
        js = out / f"frontier_{arm}_cap{cap}.json"
        js.write_text(json.dumps(frontier_summary(df, arm, cap), indent=1), encoding="utf-8")
        written += [md, csv, js]
    png = out / f"F2_pareto_{arm}.png"
    f2_figure(df, arm, capacities, png)
    written.append(png)
    return written
