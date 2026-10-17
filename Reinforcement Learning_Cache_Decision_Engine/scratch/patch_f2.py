import pathlib
p = pathlib.Path("src/rlcache/analysis/report.py")
s = p.read_text(encoding="utf-8")
old = '''        b = pm[pm.policy_class == "bound"]
        for _, r in b.iterrows():
            ax.scatter(100 * r.stale_read_rate, r.ohr, marker="D", facecolors="none", edgecolors="r", s=48)
            ax.annotate(r.policy.replace("zerostale_oracle_ttl:", "oracle-TTL ")
                        .replace("belady_ttl_constrained", "Belady-TTL").replace("belady_plain", "Belady"),
                        (100 * r.stale_read_rate, r.ohr), fontsize=6, xytext=(3, 3),
                        textcoords="offset points")'''
new = '''        b = pm[pm.policy_class == "bound"]
        xmax = 1.25 * 100 * float(base.stale_read_rate.max())
        off_axis = []
        for _, r in b.iterrows():
            name = (r.policy.replace("zerostale_oracle_ttl:", "oracle-TTL ")
                    .replace("belady_ttl_constrained", "Belady-TTL").replace("belady_plain", "Belady"))
            x = 100 * r.stale_read_rate
            if x > xmax:                       # keep the frontier legible; never drop a bound silently
                off_axis.append(f"{name}: stale {x:.1f}%, OHR {r.ohr:.3f}")
                continue
            ax.scatter(x, r.ohr, marker="D", facecolors="none", edgecolors="r", s=48)
            ax.annotate(name, (x, r.ohr), fontsize=6, xytext=(3, 3), textcoords="offset points")
        ax.set_xlim(-0.03 * xmax, xmax)
        if off_axis:
            ax.text(0.98, 0.02 if cap != capacities[0] else 0.30, "off-axis bounds:\n" + "\n".join(off_axis),
                    transform=ax.transAxes, fontsize=6, ha="right", va="bottom", color="r")'''
assert s.count(old) == 1
p.write_text(s.replace(old, new), encoding="utf-8")
