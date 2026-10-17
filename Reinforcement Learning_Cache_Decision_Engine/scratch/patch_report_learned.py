import pathlib

p = pathlib.Path("src/rlcache/analysis/report.py")
s = p.read_text(encoding="utf-8")


def rep(a, b):
    global s
    assert s.count(a) == 1, a[:70]
    s = s.replace(a, b)


# T2: learned policies are listed individually (every pre-registered variant, no selection)
rep('''    for pol in sorted(test[test.policy_class == "bound"].policy.unique()):
        rows.append((pol, "bound", test[test.policy == pol]))''',
    '''    for pol in sorted(test[test.policy_class == "learned"].policy.unique()):
        rows.append((pol, "learned", test[test.policy == pol]))
    for pol in sorted(test[test.policy_class == "bound"].policy.unique()):
        rows.append((pol, "bound", test[test.policy == pol]))''')

# F2: draw learned points
rep('''        b = pm[pm.policy_class == "bound"]
        xmax = 1.25 * 100 * float(base.stale_read_rate.max())''',
    '''        for _, r in pm[pm.policy_class == "learned"].iterrows():
            ax.scatter(100 * r.stale_read_rate, r.ohr, marker="*", s=150, c="gold", edgecolors="k",
                       zorder=5)
            ax.annotate(r.policy.replace("tabq:", "tabQ "), (100 * r.stale_read_rate, r.ohr), fontsize=6,
                        xytext=(4, -9), textcoords="offset points")
        b = pm[pm.policy_class == "bound"]
        xmax = 1.25 * 100 * float(max(base.stale_read_rate.max(),
                                       pm[pm.policy_class == "learned"].stale_read_rate.max()
                                       if (pm.policy_class == "learned").any() else 0.0))''')

rep('''def f2_figure(''', '''def learned_vs_baselines(df: pd.DataFrame, policy: str, arm: str, capacity: float,
                        n_boot: int = 10_000) -> dict:
    """Pre-registered statistic (M6-4) and head-to-head comparisons for ONE learned policy on the
    test split: paired by seed, bootstrap CI of the mean paired difference."""
    from .signal import paired_bootstrap_ci

    d = paired_delta(df, policy, arm, capacity)
    out: dict = {"policy": policy, "capacity": capacity, "n_seeds": int(len(d))}
    if d.empty:
        return out
    lo, hi = paired_bootstrap_ci(d.delta_ohr.to_numpy(), n_boot=n_boot)
    out.update(delta_ohr_mean=float(d.delta_ohr.mean()), delta_ohr_ci=(lo, hi),
               n_beyond_frontier=int(d.beyond_frontier.sum()),
               n_above_envelope=int((d.delta_ohr > 0).sum()))
    t = _slice(df, "test", arm, capacity)
    mine = t[t.policy == policy].set_index("seed")
    for ref in ("random:45", "fixed:redis/3600s/normal", "place_size:p25", "place_hash:0.10"):
        r = t[t.policy == ref].set_index("seed")
        common = mine.index.intersection(r.index)
        if len(common) == 0:
            continue
        for col in ("utility", "ohr", "stale_read_rate"):
            dd = (mine.loc[common, col] - r.loc[common, col]).to_numpy()
            l, h = paired_bootstrap_ci(dd, n_boot=n_boot)
            out[f"d_{col}_vs_{ref}"] = (float(dd.mean()), l, h, int((dd > 0).sum()))
    return out


def f2_figure(''')
p.write_text(s, encoding="utf-8")
print("ok")
